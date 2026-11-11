import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api/client";
import { useLoad, useRunStream } from "../lib/hooks";
import { Badge, ErrorBox, Loading, Score, SourceBadge, actionTone, budgetText } from "../components/ui";
import { RunTimeline } from "../components/RunTimeline";

type Match = { requirement: string; strength: string; evidence_ids: string[]; project_ids: string[]; note: string };

export default function JobDetail() {
  const { id = "" } = useParams();
  const { data, error, loading, reload } = useLoad(() => api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id } } }), [id], 4000);
  const { events, connected } = useRunStream(data?.row?.thread_id);
  if (loading && !data) return <Loading />;
  if (error) return (
    <section>
      <ErrorBox error={error} onRetry={reload} />
      <button className="btn" onClick={async () => { await api.POST("/api/jobs/{job_id}/analyse", { params: { path: { job_id: id } } }); reload(); }}>Analyse this job</button>
    </section>);
  if (!data) return null;
  const s = data.state as Record<string, any>;
  const spec = s.job_spec ?? {}, risk = s.risk ?? {}, fit = s.fit ?? {}, price = s.price, dec = s.decision ?? {};
  const ev: Record<string, string> = s.evidence ?? {};
  const job = data.job as Record<string, any>;
  return (
    <section className="detail">
      <div className="page-head">
        <h1>{job.title}</h1>
        <div className="actions">
          <SourceBadge source={job.source} url={job.source_url} />
          <Badge tone={actionTone(dec.action)}>{dec.action ?? s.status}</Badge>
          {data.interrupt && <Link className="btn primary" to={`/studio/${id}`}>Open proposal studio</Link>}
        </div>
      </div>
      <div className="grid2">
        <div className="card">
          <h2>Job post <span className="muted small">(untrusted text)</span></h2>
          <p className="post">{job.description}</p>
          <p className="small muted">{budgetText(job.budget)} · {job.connects_cost} Connects · {job.proposals_count} proposals · client {job.client_id}</p>
        </div>
        <div className="card">
          <h2>Bid or skip</h2>
          <ul className="reasons">{(dec.reasons ?? []).map((r: string) => <li key={r}>{r}</li>)}</ul>
          <h3>JobSpec</h3>
          <dl className="kv">
            <dt>Requirements</dt><dd>{(spec.requirements ?? []).join(", ") || "–"}</dd>
            <dt>Hidden needs</dt><dd>{(spec.hidden_needs ?? []).join(", ") || "none detected"}</dd>
            <dt>Deliverables</dt><dd>{(spec.deliverables ?? []).join(" / ") || "–"}</dd>
            <dt>Screening</dt><dd>{(spec.screening_questions ?? []).join(" / ") || "none"}</dd>
          </dl>
        </div>
        <div className="card">
          <h2>Risk report <Score value={risk.risk_score} invert label="risk" /></h2>
          <div className="chips">{(risk.flags ?? []).map((f: string) => <Badge key={f} tone={f === "prompt_injection" || risk.is_scam ? "bad" : "warn"}>{f.replace(/_/g, " ")}</Badge>)}</div>
          <ul className="reasons">{(risk.reasons ?? []).map((r: string) => <li key={r}>{r}</li>)}</ul>
          <p className="small">Client quality: {risk.client_quality ?? "–"} {risk.injection_detected && <Badge tone="bad">instructions aimed at AI were ignored</Badge>}</p>
        </div>
        <div className="card">
          <h2>Price rationale</h2>
          {price ? (<>
            <p><strong>${price.amount}{price.unit === "hour" ? "/h" : ""}</strong> (floor ${price.floor}{price.unit === "hour" ? "/h" : ""}, {price.market_source === "real" ? "real contracts" : "market"} p25/p50/p75 {price.market_p25}/{price.market_p50}/{price.market_p75})</p>
            <p className="small">{price.connects_cost} Connects · worth it: <Badge tone={price.connects_worth_it ? "good" : "warn"}>{String(price.connects_worth_it)}</Badge> · EV ${price.expected_value_usd}</p>
            <p className="muted small">{price.rationale}</p></>) : <p className="muted">No price: the job was not recommended for a bid.</p>}
        </div>
      </div>
      <div className="card">
        <h2>Requirement → evidence matrix <Score value={fit.fit_score} label="fit" /></h2>
        <div className="table-wrap">
          <table className="matrix">
            <thead><tr><th>Requirement</th><th>Strength</th><th>Portfolio evidence that proves it</th></tr></thead>
            <tbody>
              {(fit.matches ?? []).map((m: Match) => (
                <tr key={m.requirement}>
                  <td>{m.requirement}</td>
                  <td><Badge tone={m.strength === "strong" ? "good" : m.strength === "partial" ? "warn" : "bad"}>{m.strength}</Badge></td>
                  <td>{m.evidence_ids.length ? m.evidence_ids.map((e) => <details key={e}><summary>{e}</summary><p className="small">{ev[e] ?? "(not loaded)"}</p></details>) : <span className="muted">no evidence – will not be claimed</span>}</td>
                </tr>))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="card">
        <h2>Agent run</h2>
        <RunTimeline events={events} connected={connected} />
        <ol className="log">{(s.log ?? []).map((l: { node: string; msg: string }, i: number) => <li key={i}><strong>{l.node}</strong> <span className="muted">{l.msg}</span></li>)}</ol>
      </div>
    </section>
  );
}
