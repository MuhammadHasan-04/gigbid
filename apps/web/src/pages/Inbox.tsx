import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api/client";
import { useLoad } from "../lib/hooks";
import { Badge, Empty, ErrorBox, Loading, Score, SourceBadge, actionTone, budgetText } from "../components/ui";

export default function Inbox() {
  const { data, error, loading, reload } = useLoad(() => api.GET("/api/jobs"), [], 5000);
  const [filter, setFilter] = useState<"all" | "bid" | "watch" | "skip" | "attention">("all");
  const [busy, setBusy] = useState(false);
  const rows = useMemo(() => (data ?? []).filter((r) =>
    filter === "all" ? true : filter === "attention" ? ["needs_attention", "dead_letter", "awaiting_approval"].includes(r.status ?? "") : r.action === filter), [data, filter]);
  async function scout() { setBusy(true); await api.POST("/api/jobs/scout"); setTimeout(() => { setBusy(false); reload(); }, 1500); }
  async function skip(id: string) { await api.POST("/api/jobs/{job_id}/retry", { params: { path: { job_id: id } } }); reload(); }
  return (
    <section>
      <div className="page-head">
        <h1>Job inbox</h1>
        <div className="actions">
          <div className="seg" role="group" aria-label="Filter">
            {(["all", "bid", "watch", "skip", "attention"] as const).map((f) => (
              <button key={f} className={filter === f ? "active" : ""} aria-pressed={filter === f} onClick={() => setFilter(f)}>{f}</button>))}
          </div>
          <button className="btn primary" onClick={scout} disabled={busy}>{busy ? "Scouting…" : "Scout now"}</button>
        </div>
      </div>
      {loading && !data ? <Loading /> : error ? <ErrorBox error={error} onRetry={reload} /> : rows.length === 0 ? (
        <Empty title="No jobs yet">Click “Scout now” or wait for the next scheduled scout. New jobs are analysed in the background.</Empty>
      ) : (
        <ul className="job-list">
          {rows.map((r) => (
            <li key={r.job_id} className="card job" data-testid="job-row">
              <div className="job-main">
                <Link to={`/jobs/${r.job_id}`} className="job-title">{r.title ?? r.job_id}</Link>
                <div className="chips">
                  <Badge tone={actionTone(r.action)}>{r.action ?? r.status}</Badge>
                  <Score value={r.fit_score} label="fit" />
                  <Score value={r.risk_score} invert label="risk" />
                  <SourceBadge source={r.source} />
                  {r.is_scam && <Badge tone="bad">scam</Badge>}
                  {(r.flags ?? []).filter((f) => f !== "low_budget").slice(0, 3).map((f) => <Badge key={f} tone={f === "prompt_injection" ? "bad" : "warn"}>{f.replace(/_/g, " ")}</Badge>)}
                </div>
                <div className="muted small">{(r.reasons ?? []).join(" · ") || r.status}</div>
              </div>
              <div className="job-side">
                {r.budget && <div className="small">{budgetText(r.budget as any)}</div>}
                {r.price ? <div><strong>${r.price.toFixed(0)}{(r.budget as any)?.type === "hourly" ? "/h" : ""}</strong> <span className="muted small">suggested</span></div> : null}
                {r.connects_cost != null && <div className="small muted">{r.connects_cost} Connects</div>}
                {r.status === "awaiting_approval" && <Link className="btn small primary" to={`/studio/${r.job_id}`}>Review draft</Link>}
                {["dead_letter", "needs_attention"].includes(r.status ?? "") && <button className="btn small" onClick={() => skip(r.job_id)}>Retry</button>}
                {r.status === "analysing" && <span className="muted small"><span className="spinner" aria-hidden /> analysing</span>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
