import { api } from "../lib/api/client";
import { useLoad } from "../lib/hooks";
import { ErrorBox, Loading } from "../components/ui";

function Bar({ value, max }: { value: number; max: number }) {
  return <span className="bar" aria-hidden><span style={{ width: `${max ? (100 * value) / max : 0}%` }} /></span>;
}

export default function Analytics() {
  const { data, error, loading, reload } = useLoad(() => api.GET("/api/analytics"), [], 15000);
  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox error={error} onRetry={reload} />;
  const f = data.funnel as Record<string, number>;
  const maxF = Math.max(1, ...Object.values(f));
  const c = data.cost_latency as Record<string, number | null>;
  return (
    <section>
      <div className="page-head"><h1>Analytics</h1></div>
      <div className="grid2">
        <div className="card">
          <h2>Funnel</h2>
          <table><tbody>{Object.entries(f).map(([k, v]) => <tr key={k}><td>{k}</td><td className="num">{v}</td><td className="w"><Bar value={v} max={maxF} /></td></tr>)}</tbody></table>
        </div>
        <div className="card">
          <h2>Connects</h2>
          <p>Spent <strong>{(data.connects as any).spent}</strong> of weekly budget {(data.connects as any).weekly_budget} · per reply {(data.connects as any).per_reply ?? "–"}</p>
          <h2>Cost and latency</h2>
          <dl className="kv">
            <dt>p50 / p95 latency per job</dt><dd>{c.p50_latency_s_per_job ?? "–"}s / {c.p95_latency_s_per_job ?? "–"}s</dd>
            <dt>p95 latency per proposal</dt><dd>{c.p95_latency_s_per_proposal ?? "–"}s</dd>
            <dt>USD per job / per proposal</dt><dd>${c.usd_per_job ?? 0} / ${c.usd_per_proposal ?? 0}</dd>
            <dt>Tokens per job</dt><dd>{c.tokens_per_job ?? "–"}</dd>
          </dl>
        </div>
      </div>
      <div className="card">
        <h2>Reply and hire rate by category</h2>
        <div className="table-wrap"><table>
          <thead><tr><th>Category</th><th>Sent</th><th>Replied</th><th>Hired</th><th>Reply rate</th><th>Connects</th></tr></thead>
          <tbody>{(data.by_category as any[]).map((r) => <tr key={r.category}><td>{r.category}</td><td>{r.sent}</td><td>{r.replied}</td><td>{r.hired}</td>
            <td>{r.reply_rate != null ? (100 * r.reply_rate).toFixed(0) + "%" : "–"}</td><td>{r.connects}</td></tr>)}</tbody>
        </table></div>
      </div>
      <div className="card">
        <h2>Top rejection and skip reasons</h2>
        <ul>{(data.rejection_reasons as any[]).map((r, i) => <li key={i}>{r.reason} <span className="muted small">({r.kind}, {r.n})</span></li>)}</ul>
      </div>
    </section>
  );
}
