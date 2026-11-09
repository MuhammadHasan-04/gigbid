import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errorText } from "../lib/api/client";
import { useMe } from "../App";

const PERSONAS = [
  { id: "ai_ml", title: "AI/ML engineer", text: "LLM apps, RAG, classical ML, computer vision. Floor $45/h." },
  { id: "fullstack", title: "Full-stack web developer", text: "React, Node, Django, payments, real-time. Floor $35/h." },
  { id: "data_analyst", title: "Data analyst", text: "BI dashboards, SQL, dbt, experimentation. Floor $30/h." },
] as const;

export default function Onboarding() {
  const { setMe } = useMe();
  const nav = useNavigate();
  const [persona, setPersona] = useState<(typeof PERSONAS)[number]["id"]>("ai_ml");
  const [marketplace, setMarketplace] = useState<"gigsim" | "upwork_live">("gigsim");
  const [floor, setFloor] = useState<string>("");
  const [budget, setBudget] = useState(80);
  const [query, setQuery] = useState("");
  const [minBudget, setMinBudget] = useState(0);
  const [err, setErr] = useState("");
  async function save(e: React.FormEvent) {
    e.preventDefault();
    const r = await api.POST("/api/auth/onboard", { body: { persona, marketplace, hourly_floor: floor ? Number(floor) : null,
      weekly_connects_budget: budget, saved_search_query: query, min_budget: minBudget } });
    if (r.error || !r.data) return setErr(errorText(r.error));
    setMe(r.data);
    await api.POST("/api/jobs/scout");
    nav("/inbox");
  }
  return (
    <div className="auth">
      <form className="card onboarding form" onSubmit={save}>
        <h1>Set up GigBid</h1>
        <fieldset>
          <legend>1. Portfolio</legend>
          <p className="muted small">Pick a demo persona (CV, case studies, repos, past proposals) or upload your own work later in Settings.</p>
          <div className="persona-grid">
            {PERSONAS.map((p) => (
              <label key={p.id} className={`persona ${persona === p.id ? "active" : ""}`}>
                <input type="radio" name="persona" value={p.id} checked={persona === p.id} onChange={() => setPersona(p.id)} />
                <strong>{p.title}</strong><span className="muted small">{p.text}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <legend>2. Marketplace</legend>
          <label className="row"><input type="radio" checked={marketplace === "gigsim"} onChange={() => setMarketplace("gigsim")} /> GigSim (simulator, safe)</label>
          <label className="row"><input type="radio" checked={marketplace === "upwork_live"} onChange={() => setMarketplace("upwork_live")} /> Upwork (official MCP server, OAuth; connect in Settings)</label>
        </fieldset>
        <fieldset>
          <legend>3. Rates, filters and budget</legend>
          <label>Hourly floor (USD, blank = persona default)<input inputMode="decimal" value={floor} onChange={(e) => setFloor(e.target.value)} /></label>
          <label>Weekly Connects budget<input type="number" min={0} value={budget} onChange={(e) => setBudget(Number(e.target.value))} /></label>
          <label>Saved search keywords (blank = all new jobs)<input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. dashboard" /></label>
          <label>Ignore jobs with budget below (USD)<input type="number" min={0} value={minBudget} onChange={(e) => setMinBudget(Number(e.target.value))} /></label>
        </fieldset>
        {err && <div className="state error" role="alert">{err}</div>}
        <button className="btn primary">Start scouting</button>
      </form>
    </div>
  );
}
