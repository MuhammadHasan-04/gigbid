import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, errorText, type Schemas } from "../lib/api/client";
import { useLoad } from "../lib/hooks";
import { useMe } from "../App";
import { EvidenceText } from "../components/EvidenceText";
import { Badge, Empty, ErrorBox, Loading } from "../components/ui";

type Approval = Schemas["Approval"];

export default function Studio() {
  const { id } = useParams();
  const { data, error, loading, reload } = useLoad(() => api.GET("/api/approvals"), [], 5000);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  const list = (data ?? []).filter((a) => a.kind === "proposal");
  const current = id ? list.find((a) => a.thread_id.endsWith(":" + id)) : undefined;
  return (
    <section>
      <div className="page-head"><h1>Proposal studio</h1><span className="muted">{list.length} waiting for approval</span></div>
      {id && current ? <ApprovalPanel key={current.thread_id} a={current} onDone={reload} /> : id ? (
        <Empty title="Nothing waiting on this job">It may already be approved, or still being drafted. <Link to={`/jobs/${id}`}>Open job</Link></Empty>
      ) : list.length === 0 ? <Empty title="No drafts waiting">When GigBid recommends a bid, the draft shows up here for your approval.</Empty> : (
        <ul className="job-list">{list.map((a) => (
          <li key={a.thread_id} className="card job"><div className="job-main"><Link className="job-title" to={`/studio/${a.thread_id.split(":").pop()}`}>{a.title}</Link>
            <div className="chips"><Badge tone={(a.payload as any).compliance?.allowed ? "good" : "bad"}>{(a.payload as any).compliance?.allowed ? "compliant" : "blocked"}</Badge>
              <Badge>${(a.payload as any).price?.amount}{(a.payload as any).price?.unit === "hour" ? "/h" : ""}</Badge><Badge>{(a.payload as any).dry_run?.connects_cost} Connects</Badge></div></div></li>))}</ul>
      )}
    </section>
  );
}

function ApprovalPanel({ a, onDone }: { a: Approval; onDone: () => void }) {
  const p = a.payload as Record<string, any>;
  const { me } = useMe();
  const nav = useNavigate();
  const [text, setText] = useState<string>(p.cover_letter);
  const [answers, setAnswers] = useState<string[]>(p.screening_answers ?? []);
  const [bid, setBid] = useState<number>(p.price?.amount ?? 0);
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  useEffect(() => { setText(p.cover_letter); }, [p.cover_letter]);
  const edited = text !== p.cover_letter || bid !== p.price?.amount || JSON.stringify(answers) !== JSON.stringify(p.screening_answers ?? []);
  const words = text.split(/\s+/).filter(Boolean).length;
  const sentences = useMemo(() => text.split(/(?<=[.!?])\s+/), [text]);
  const blocked = !p.compliance?.allowed && !edited;

  async function decide(action: "approve" | "edit" | "reject") {
    setBusy(true); setMsg("");
    const body = action === "reject" ? { action, reason } : action === "edit" ? { action, cover_letter: text, screening_answers: answers, bid_amount: bid } : { action };
    const r = await api.POST("/api/approvals/{thread_id}/decision", { params: { path: { thread_id: a.thread_id } }, body });
    setBusy(false);
    if (r.error) return setMsg(errorText(r.error));
    setMsg(action === "reject" ? "Rejected. Reason saved." : "Approved. Submitting through the marketplace…");
    setTimeout(() => { onDone(); nav(`/jobs/${p.job_id}`); }, 1200);
  }
  async function regen(i: number) {
    const r = await api.POST("/api/approvals/{thread_id}/regenerate", { params: { path: { thread_id: a.thread_id } }, body: { sentence_index: i, text } });
    if (r.data) setText(r.data.text); else setMsg(errorText(r.error));
  }
  const critique = (p.critiques ?? []).slice(-1)[0];
  return (
    <div className="studio">
      <div className="card editor">
        <div className="row-between"><h2>{p.title}</h2><Link to={`/jobs/${p.job_id}`} className="small">job detail →</Link></div>
        <label htmlFor="cover">Cover letter <span className="muted small">({words} words · hover a citation to see its evidence)</span></label>
        <textarea id="cover" data-testid="cover-editor" value={text} onChange={(e) => setText(e.target.value)} rows={10} />
        <div className="preview" aria-label="Preview with evidence">
          <EvidenceText text={text} evidence={p.evidence ?? {}} claims={p.claims} />
        </div>
        <details>
          <summary>Regenerate one sentence</summary>
          <ol className="regen">{sentences.map((s, i) => <li key={i}><span className="small">{s}</span> <button className="btn small ghost" onClick={() => regen(i)}>regenerate</button></li>)}</ol>
        </details>
        {answers.length > 0 && <>
          <h3>Screening answers</h3>
          {answers.map((ans, i) => <textarea key={i} aria-label={`Screening answer ${i + 1}`} value={ans} rows={3} onChange={(e) => setAnswers(answers.map((x, j) => j === i ? e.target.value : x))} />)}
        </>}
        <label>{p.price?.unit === "hour" ? "Hourly rate (USD/h)" : "Bid (USD)"}<input type="number" min={1} value={bid} onChange={(e) => setBid(Number(e.target.value))} /></label>
      </div>
      <aside className="side">
        <div className="card">
          <h3>Critic</h3>
          {critique ? <><p className="small">grounding {critique.grounding} · personalisation {critique.personalisation} · <Badge tone={critique.passed ? "good" : "warn"}>{critique.passed ? "passed" : "issues"}</Badge></p>
            <ul className="small">{(critique.issues ?? []).map((x: string) => <li key={x}>{x}</li>)}</ul>
            <p className="muted small">{(p.critiques ?? []).length - 1} revision(s) requested</p></> : <p className="muted">–</p>}
        </div>
        <div className="card">
          <h3>Compliance <Badge tone={p.compliance?.allowed ? "good" : "bad"}>{p.compliance?.allowed ? "ok" : "blocked"}</Badge></h3>
          {p.compliance?.blocked_reason && <p className="bad small" role="alert">{p.compliance.blocked_reason}</p>}
          <ul className="small">{(p.compliance?.violations ?? []).map((v: any, i: number) => <li key={i}><Badge tone="warn">{v.rule}</Badge> removed: “{v.sentence}”</li>)}</ul>
          {(p.removed_claims ?? []).length > 0 && <><h4>Unsupported claims removed by the verifier</h4>
            <ul className="small">{p.removed_claims.map((c: any, i: number) => <li key={i}>“{c.text}” <span className="muted">({c.reason})</span></li>)}</ul></>}
        </div>
        <div className="card" data-testid="dry-run">
          <h3>What will be sent (dry run)</h3>
          <p className="small">Job {p.job_id} · bid <strong>${bid}{p.price?.unit === "hour" ? "/h" : ""}</strong> · <strong>{p.dry_run?.connects_cost}</strong> Connects (balance {p.dry_run?.connects_balance ?? "?"} → {(p.dry_run?.connects_balance ?? 0) - (p.dry_run?.connects_cost ?? 0)})</p>
          <p className="small muted">Weekly Connects budget: {me?.settings.weekly_connects_budget}. Approving submits through the marketplace MCP server with an idempotency key; it can never be sent twice.</p>
          <p className="small">Risk {p.risk?.risk_score} · fit {p.fit?.fit_score} · {p.price?.rationale}</p>
        </div>
        <div className="card actions-card">
          {msg && <p role="status" className="small">{msg}</p>}
          {edited ? <button className="btn primary" disabled={busy} onClick={() => decide("edit")} data-testid="approve-edited">Approve with my edits</button>
            : <button className="btn primary" disabled={busy || blocked} onClick={() => decide("approve")} data-testid="approve">Approve and send</button>}
          {blocked && <p className="small bad">Compliance blocked this draft. Edit it to fix the issue, or reject it.</p>}
          {!rejecting ? <button className="btn danger" onClick={() => setRejecting(true)} data-testid="reject">Reject…</button> : (
            <div className="form">
              <label>Why are you rejecting it?<input value={reason} onChange={(e) => setReason(e.target.value)} data-testid="reject-reason" /></label>
              <button className="btn danger" disabled={!reason.trim() || busy} onClick={() => decide("reject")} data-testid="reject-confirm">Reject with reason</button>
            </div>)}
        </div>
      </aside>
    </div>
  );
}
