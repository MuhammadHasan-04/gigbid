import { useEffect, useState } from "react";
import { api, errorText, type Schemas } from "../lib/api/client";
import { useLoad } from "../lib/hooks";
import { useMe } from "../App";
import { Badge, ErrorBox, Loading } from "../components/ui";

export default function Settings() {
  const { me } = useMe();
  const s = useLoad(() => api.GET("/api/settings"), []);
  const mem = useLoad(() => api.GET("/api/memory"), []);
  const [form, setForm] = useState<Schemas["SettingsModel"] | null>(null);
  const [msg, setMsg] = useState("");
  const [up, setUp] = useState({ title: "", text: "", industry: "" });
  useEffect(() => { if (s.data) setForm(s.data); }, [s.data]);
  if (s.loading || !form) return <Loading />;
  if (s.error) return <ErrorBox error={s.error} />;
  async function save() {
    const r = await api.PUT("/api/settings", { body: form! });
    setMsg(r.error ? errorText(r.error) : "Saved.");
  }
  async function forget(ns: string, key: string) {
    await api.DELETE("/api/memory/{namespace}/{key}", { params: { path: { namespace: ns, key } } });
    mem.reload();
  }
  async function upload(e: React.FormEvent) {
    e.preventDefault();
    const r = await api.POST("/api/portfolio/upload", { body: { title: up.title, text: up.text, industry: up.industry || null } });
    setMsg(r.error ? errorText(r.error) : (r.data?.detail ?? "Added."));
    setUp({ title: "", text: "", industry: "" });
  }
  async function connectUpwork() {
    const r = await api.GET("/api/auth/upwork/start");
    if (r.data && (r.data as any).url) location.assign((r.data as any).url); else setMsg(errorText(r.error));
  }
  const ss = form.saved_searches[0] ?? { id: "s1", query: "", every_minutes: 30, limit: 15 };
  return (
    <section className="settings">
      <div className="page-head"><h1>Settings</h1>{msg && <span role="status" className="small">{msg}</span>}</div>
      <div className="grid2">
        <div className="card form">
          <h2>Autonomy and budgets</h2>
          <label>Autonomy
            <select value={form.autonomy} onChange={(e) => setForm({ ...form, autonomy: e.target.value as any })}>
              <option value="suggest">Suggest only (default)</option>
              <option value="auto_skip_low_fit">Auto-skip low-fit jobs (never auto-send)</option>
            </select></label>
          <label>Hourly floor (USD)<input type="number" value={form.hourly_floor ?? ""} onChange={(e) => setForm({ ...form, hourly_floor: e.target.value ? Number(e.target.value) : null })} /></label>
          <label>Weekly Connects budget<input type="number" value={form.weekly_connects_budget} onChange={(e) => setForm({ ...form, weekly_connects_budget: Number(e.target.value) })} /></label>
          <h2>Saved search</h2>
          <label>Keywords<input value={ss.query} onChange={(e) => setForm({ ...form, saved_searches: [{ ...ss, query: e.target.value }] })} /></label>
          <label>Every (minutes, min 15; live mode at least 240)<input type="number" min={15} value={ss.every_minutes} onChange={(e) => setForm({ ...form, saved_searches: [{ ...ss, every_minutes: Number(e.target.value) }] })} /></label>
          <button className="btn primary" onClick={save}>Save settings</button>
        </div>
        <div className="card">
          <h2>Connected accounts</h2>
          <p>Marketplace mode: <Badge>{form.marketplace}</Badge></p>
          <p>Upwork (official MCP server, OAuth 2.1): <Badge tone={me?.upwork_connected ? "good" : "neutral"}>{me?.upwork_connected ? "connected" : "not connected"}</Badge></p>
          <button className="btn" onClick={connectUpwork}>Connect Upwork</button>
          <p className="small muted">Live mode only creates drafts that you confirm on Upwork. No scraping, no browser automation.</p>
          <h2>Add work to your portfolio</h2>
          <form className="form" onSubmit={upload}>
            <label>Title<input required minLength={3} value={up.title} onChange={(e) => setUp({ ...up, title: e.target.value })} /></label>
            <label>Industry<input value={up.industry} onChange={(e) => setUp({ ...up, industry: e.target.value })} /></label>
            <label>What you did (case study text)<textarea required minLength={20} rows={4} value={up.text} onChange={(e) => setUp({ ...up, text: e.target.value })} /></label>
            <button className="btn">Add and re-index</button>
          </form>
        </div>
      </div>
      <div className="card">
        <h2>What GigBid has learned</h2>
        {mem.loading ? <Loading /> : mem.error ? <ErrorBox error={mem.error} /> : (
          <div className="grid2">
            <div><h3>Style rules (promoted)</h3>
              {(mem.data?.style ?? []).length === 0 ? <p className="muted small">None yet. A pattern is promoted after it appears in 2 of your edits.</p> :
                <ul>{mem.data!.style.map((r: any) => <li key={r.key}>{r.rule} <span className="muted small">{r.because}</span> <button className="btn small ghost" onClick={() => forget("style", r.key)} aria-label={`Delete rule ${r.rule}`}>delete</button></li>)}</ul>}
              <h3>Candidates</h3>
              <ul className="small">{(mem.data?.style_candidates ?? []).map((r: any) => <li key={r.key}>{r.rule} <span className="muted">({r.count} edit{r.count === 1 ? "" : "s"})</span> <button className="btn small ghost" onClick={() => forget("style_candidates", r.key)}>delete</button></li>)}</ul>
            </div>
            <div><h3>Outcome memory</h3>
              <ul className="small">{(mem.data?.outcome ?? []).map((r: any) => <li key={r.key}><strong>{r.key}</strong>: sent {r.sent}, replied {r.replied}, hired {r.hired} ({r.exemplars?.length ?? 0} exemplars) <button className="btn small ghost" onClick={() => forget("outcome", r.key)}>delete</button></li>)}</ul>
              <h3>Recent edits</h3>
              <ul className="small">{(mem.data?.edits ?? []).slice(-5).map((r: any) => <li key={r.key}>{r.job_id}: {(r.patterns ?? []).join(", ") || "no pattern"}</li>)}</ul>
            </div>
          </div>)}
      </div>
    </section>
  );
}
