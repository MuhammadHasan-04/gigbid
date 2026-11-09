import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errorText, setToken } from "../lib/api/client";
import { useMe } from "../App";

export default function Login() {
  const { setMe } = useMe();
  const nav = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    const r = mode === "login"
      ? await api.POST("/api/auth/login", { body: { email, password } })
      : await api.POST("/api/auth/register", { body: { email, password, name } });
    setBusy(false);
    if (r.error || !r.data) { setErr(errorText(r.error)); return; }
    setToken(r.data.token);
    setMe(r.data.user);
    nav(r.data.user.persona ? "/inbox" : "/onboarding");
  }
  return (
    <div className="auth">
      <div className="card auth-card">
        <h1 className="brand big">Gig<span>Bid</span></h1>
        <p className="muted">A team of agents that finds freelance jobs, checks them for scams, and drafts proposals grounded in your real portfolio. Nothing is sent until you approve it.</p>
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={mode === "login"} className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>Sign in</button>
          <button role="tab" aria-selected={mode === "register"} className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>Create account</button>
        </div>
        <form onSubmit={submit} className="form">
          {mode === "register" && <label>Name<input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></label>}
          <label>Email<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></label>
          <label>Password<input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} /></label>
          {err && <div className="state error" role="alert">{err}</div>}
          <button className="btn primary" disabled={busy}>{busy ? "…" : mode === "login" ? "Sign in" : "Create account"}</button>
        </form>
      </div>
    </div>
  );
}
