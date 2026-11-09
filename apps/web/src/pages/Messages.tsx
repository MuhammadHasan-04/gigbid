import { useState } from "react";
import { api, errorText, type Schemas } from "../lib/api/client";
import { useLoad } from "../lib/hooks";
import { Badge, Empty, ErrorBox, Loading } from "../components/ui";

type Conv = Schemas["Conversation"];

export default function Messages() {
  const { data, error, loading, reload } = useLoad(() => api.GET("/api/messages"), [], 6000);
  const [sel, setSel] = useState<string | null>(null);
  async function sync() { await api.POST("/api/messages/sync"); setTimeout(reload, 2000); }
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  const list = data ?? [];
  const cur = list.find((c) => c.thread_id === sel) ?? list[0];
  return (
    <section>
      <div className="page-head"><h1>Messages</h1><button className="btn" onClick={sync}>Check for replies</button></div>
      {list.length === 0 ? <Empty title="No client conversations yet">When a client replies to a proposal, GigBid drafts a response here for you to approve.</Empty> : (
        <div className="messages">
          <ul className="threads" role="listbox" aria-label="Conversations">
            {list.map((c) => (
              <li key={c.thread_id} role="option" aria-selected={cur?.thread_id === c.thread_id}>
                <button className={cur?.thread_id === c.thread_id ? "active" : ""} onClick={() => setSel(c.thread_id)}>
                  <strong>{c.thread_id}</strong> {c.pending && <Badge tone="info">reply ready</Badge>} {c.intent && <Badge tone={c.intent === "scam_signal" ? "bad" : "neutral"}>{c.intent}</Badge>}
                  <span className="small muted">{c.last_client_msg?.slice(0, 80)}</span>
                </button>
              </li>))}
          </ul>
          {cur && <Thread c={cur} onDone={reload} />}
        </div>)}
    </section>
  );
}

function Thread({ c, onDone }: { c: Conv; onDone: () => void }) {
  const p = c.pending as Record<string, any> | null;
  const [body, setBody] = useState<string>(p?.body ?? "");
  const [slot, setSlot] = useState<string | undefined>(p?.proposed_slots?.[0]);
  const [msg, setMsg] = useState("");
  const [reason, setReason] = useState("");
  async function draft() { await api.POST("/api/messages/{thread_id}/draft", { params: { path: { thread_id: c.thread_id } } }); setMsg("Drafting a reply…"); setTimeout(onDone, 2500); }
  async function decide(action: "approve" | "edit" | "reject") {
    if (!c.graph_thread) return;
    const r = await api.POST("/api/approvals/{thread_id}/decision", { params: { path: { thread_id: c.graph_thread } },
      body: action === "reject" ? { action, reason } : { action, body, slot } });
    setMsg(r.error ? errorText(r.error) : action === "reject" ? "Discarded." : "Approved – sending.");
    setTimeout(onDone, 1500);
  }
  return (
    <div className="card thread">
      <ol className="bubbles">
        {(c.messages ?? []).map((m: any) => <li key={m.message_id} className={`bubble ${m.from}`}><span className="small muted">{m.from}</span><p>{m.body}</p></li>)}
      </ol>
      {p ? (
        <div className="reply">
          <h3>Suggested reply <Badge>{p.intent?.intent}</Badge> {p.needs_attention && <Badge tone="bad">needs attention</Badge>}</h3>
          {p.note && <p className="small muted">{p.note}</p>}
          <textarea aria-label="Reply" value={body} onChange={(e) => setBody(e.target.value)} rows={5} />
          {(p.slots ?? []).length > 0 && <fieldset><legend>Interview slot (a tentative hold is placed on your calendar)</legend>
            {(p.slots as any[]).map((s) => <label key={s.start} className="row"><input type="radio" checked={slot === s.start} onChange={() => setSlot(s.start)} /> {s.start.replace("T", " ")} ({s.timezone})</label>)}</fieldset>}
          {(p.compliance?.violations ?? []).length > 0 && <p className="small bad">Compliance removed: {(p.compliance.violations as any[]).map((v) => v.rule).join(", ")}</p>}
          <div className="row gap">
            <button className="btn primary" onClick={() => decide(body !== p.body ? "edit" : "approve")}>Approve and send</button>
            <input placeholder="reason to discard" value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Reason to discard" />
            <button className="btn danger" disabled={!reason.trim()} onClick={() => decide("reject")}>Discard</button>
          </div>
        </div>
      ) : <button className="btn" onClick={draft}>Draft a reply</button>}
      {msg && <p role="status" className="small">{msg}</p>}
    </div>
  );
}
