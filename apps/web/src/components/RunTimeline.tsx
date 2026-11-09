import { Link } from "react-router-dom";
import type { RunEvent } from "../lib/hooks";
import { Badge } from "./ui";

export function RunTimeline({ events, connected }: { events: RunEvent[]; connected: boolean }) {
  const done = [...events].reverse().find((e) => e.type === "done");
  const trace = events.find((e) => e.trace_id)?.trace_id;
  return (
    <div className="timeline" aria-live="polite">
      <div className="timeline-head">
        <Badge tone={connected ? "good" : "neutral"}>{connected ? "live" : "offline"}</Badge>
        {done ? <Badge tone="info">finished: {done.status}</Badge> : events.length ? <span className="muted"><span className="spinner" aria-hidden /> running…</span> : <span className="muted">waiting for the worker…</span>}
        {trace && <Link to={`/runs/${trace}`}>full trace →</Link>}
      </div>
      <ol>
        {events.filter((e) => e.type !== "custom").map((e, i) => (
          <li key={i} className={`tl tl-${e.type}`}>
            {e.type === "node" && <><strong>{e.node}</strong> {e.status && <Badge>{e.status}</Badge>} <span className="muted">{e.log?.msg}</span>
              {e.log?.latency_s !== undefined && <span className="muted small"> · {e.log.latency_s}s{e.log.tokens ? ` · ${e.log.tokens} tok` : ""}{e.log.providers?.length ? ` · ${e.log.providers.join(",")}` : ""}</span>}</>}
            {e.type === "interrupt" && <strong>⏸ waiting for your approval</strong>}
            {e.type === "error" && <><strong className="bad">error</strong> {e.degraded && "(marketplace unavailable – kept for retry)"} {e.error}</>}
            {e.type === "done" && <><strong>done</strong> · {e.status} {e.attention_reason && <span className="bad"> · {e.attention_reason}</span>}</>}
          </li>
        ))}
      </ol>
    </div>
  );
}
