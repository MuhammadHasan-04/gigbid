import { Link } from "react-router-dom";
import { api } from "../lib/api/client";
import { useLoad } from "../lib/hooks";
import { Empty, ErrorBox, Loading } from "../components/ui";

const COLS = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"];

export default function Pipeline() {
  const { data, error, loading, reload } = useLoad(() => api.GET("/api/pipeline"), [], 8000);
  async function sync() { await api.POST("/api/messages/sync"); setTimeout(reload, 1500); }
  if (loading && !data) return <Loading />;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  const cards = data ?? [];
  return (
    <section>
      <div className="page-head"><h1>Pipeline</h1><button className="btn" onClick={sync}>Sync marketplace events</button></div>
      {cards.length === 0 ? <Empty title="Nothing in the pipeline yet">Approved proposals appear here and move as the client views, replies or hires.</Empty> : (
        <div className="kanban" role="list">
          {COLS.map((c) => {
            const items = cards.filter((x) => x.status === c);
            return (
              <div key={c} className="col" role="listitem" aria-label={`${c}: ${items.length}`}>
                <h2>{c} <span className="muted">{items.length}</span></h2>
                {items.map((x) => (
                  <Link key={x.proposal_id} className="kcard" to={x.job_id ? (c === "drafted" ? `/studio/${x.job_id}` : `/jobs/${x.job_id}`) : "#"}>
                    <strong>{x.title}</strong>
                    <span className="small muted">{x.category} · ${x.bid?.toFixed(0)} · {x.connects ?? "?"} Connects</span>
                  </Link>))}
              </div>);
          })}
        </div>)}
    </section>
  );
}
