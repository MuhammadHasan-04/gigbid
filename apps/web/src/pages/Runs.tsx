import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api/client";
import { useLoad, useRunStream } from "../lib/hooks";
import { Badge, Empty, ErrorBox, Loading } from "../components/ui";
import { RunTimeline } from "../components/RunTimeline";

export default function Runs() {
  const { id } = useParams();
  return id ? <Trace traceId={id} /> : <RunList />;
}

function RunList() {
  const { data, error, loading, reload } = useLoad(() => api.GET("/api/runs"), [], 4000);
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  const rows = (data ?? []) as Record<string, any>[];
  const live = rows.find((r) => r.status === "analysing");
  return (
    <section>
      <div className="page-head"><h1>Agent runs</h1></div>
      {live && <div className="card"><h2>Live: {live.title}</h2><Live thread={live.thread_id} /></div>}
      {rows.length === 0 ? <Empty title="No runs yet" /> : (
        <div className="table-wrap"><table>
          <thead><tr><th>Job</th><th>Status</th><th>Tokens</th><th>USD</th><th>Latency</th><th>Trace</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.trace_id}><td><Link to={`/jobs/${r.job_id}`}>{r.title ?? r.job_id}</Link></td><td><Badge>{r.status}</Badge></td>
              <td>{r.tokens ?? 0}</td><td>{(r.usd ?? 0).toFixed(5)}</td><td>{r.latency_s ? r.latency_s.toFixed(1) + "s" : "–"}</td>
              <td><Link to={`/runs/${r.trace_id}`}>{r.trace_id}</Link></td></tr>))}</tbody>
        </table></div>)}
    </section>
  );
}

function Live({ thread }: { thread: string }) {
  const { events, connected } = useRunStream(thread);
  return <RunTimeline events={events} connected={connected} />;
}

function Trace({ traceId }: { traceId: string }) {
  const { data, error, loading } = useLoad(() => api.GET("/api/runs/trace/{trace_id}", { params: { path: { trace_id: traceId } } }), [traceId]);
  if (loading) return <Loading />;
  if (error || !data) return <ErrorBox error={error} />;
  const t0 = data.spans[0]?.ts ?? 0;
  return (
    <section>
      <div className="page-head"><h1>Trace <code>{traceId}</code></h1><Link to="/runs">all runs</Link></div>
      <div className="card">
        <p>{data.spans.length} spans · {String(data.summary.tokens)} tokens · ${Number(data.summary.usd).toFixed(5)}</p>
        <div className="table-wrap"><table>
          <thead><tr><th>Node</th><th>Calls</th><th>Tokens in/out</th><th>USD</th><th>Model latency</th></tr></thead>
          <tbody>{Object.entries(data.summary.by_node as Record<string, any>).map(([n, v]) => (
            <tr key={n}><td>{n}</td><td>{v.calls}</td><td>{v.tokens_in}/{v.tokens_out}</td><td>{v.usd.toFixed(6)}</td><td>{v.latency_s.toFixed(2)}s</td></tr>))}</tbody>
        </table></div>
      </div>
      <ol className="spans">
        {data.spans.map((s, i) => (
          <li key={i} className={`span span-${s.kind}`}>
            <span className="small muted">+{(s.ts - t0).toFixed(2)}s</span> <Badge tone={s.kind.includes("error") ? "bad" : s.kind === "tool" ? "info" : "neutral"}>{s.kind}</Badge>
            <strong> {s.node ? s.node + " · " : ""}{s.name}</strong>
            <details><summary className="small">details</summary><pre>{JSON.stringify(s.data, null, 1)}</pre></details>
          </li>))}
      </ol>
    </section>
  );
}
