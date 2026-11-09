import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { BrowserRouter, Navigate, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { api, getToken, setToken, type Schemas } from "./lib/api/client";
import { useLoad } from "./lib/hooks";
import { Loading } from "./components/ui";
import Login from "./pages/Login";
import Onboarding from "./pages/Onboarding";
import Inbox from "./pages/Inbox";
import JobDetail from "./pages/JobDetail";
import Studio from "./pages/Studio";
import Pipeline from "./pages/Pipeline";
import Messages from "./pages/Messages";
import Runs from "./pages/Runs";
import Analytics from "./pages/Analytics";
import Settings from "./pages/Settings";

type Me = Schemas["UserOut"];
const MeCtx = createContext<{ me: Me | null; setMe: (m: Me | null) => void }>({ me: null, setMe: () => {} });
export const useMe = () => useContext(MeCtx);

function DegradedBanner() {
  const { data, error } = useLoad(() => api.GET("/api/health"), [], 15000);
  const down = error || (data && !data.marketplace?.ok);
  if (!down) return null;
  return (
    <div className="banner" role="alert" data-testid="degraded-banner">
      <strong>Marketplace unavailable.</strong> GigBid can’t reach the marketplace right now. New runs are kept and will retry;
      nothing is sent while it’s down. {data?.marketplace?.error ? <span className="muted">({String(data.marketplace.error)})</span> : null}
    </div>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const { me, setMe } = useMe();
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  useEffect(() => setOpen(false), [loc.pathname]);
  const links: [string, string][] = [["/inbox", "Inbox"], ["/studio", "Approvals"], ["/pipeline", "Pipeline"], ["/messages", "Messages"],
    ["/runs", "Runs"], ["/analytics", "Analytics"], ["/settings", "Settings"]];
  return (
    <div className="shell">
      <a className="skip" href="#main">Skip to content</a>
      <header className="top">
        <NavLink to="/inbox" className="brand">Gig<span>Bid</span></NavLink>
        <button className="btn ghost menu" aria-expanded={open} aria-controls="nav" onClick={() => setOpen(!open)}>Menu</button>
        <nav id="nav" className={open ? "open" : ""} aria-label="Main">
          {links.map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}
        </nav>
        <div className="who">
          <span className="muted small">{me?.name || me?.email} · {me?.persona}</span>
          <button className="btn ghost small" onClick={() => { setToken(null); setMe(null); }}>Sign out</button>
        </div>
      </header>
      <DegradedBanner />
      <main id="main" tabIndex={-1}>{children}</main>
    </div>
  );
}

function Guard({ children }: { children: ReactNode }) {
  const { me } = useMe();
  if (!getToken() || !me) return <Navigate to="/login" replace />;
  if (!me.persona) return <Navigate to="/onboarding" replace />;
  return <Shell>{children}</Shell>;
}

export default function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!getToken()) { setReady(true); return; }
    api.GET("/api/auth/me").then((r) => { if (r.data) setMe(r.data); setReady(true); }).catch(() => setReady(true));
  }, []);
  if (!ready) return <Loading label="Starting GigBid…" />;
  return (
    <MeCtx.Provider value={{ me, setMe }}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={me ? <Navigate to={me.persona ? "/inbox" : "/onboarding"} /> : <Login />} />
          <Route path="/onboarding" element={me ? <Onboarding /> : <Navigate to="/login" />} />
          <Route path="/inbox" element={<Guard><Inbox /></Guard>} />
          <Route path="/jobs/:id" element={<Guard><JobDetail /></Guard>} />
          <Route path="/studio" element={<Guard><Studio /></Guard>} />
          <Route path="/studio/:id" element={<Guard><Studio /></Guard>} />
          <Route path="/pipeline" element={<Guard><Pipeline /></Guard>} />
          <Route path="/messages" element={<Guard><Messages /></Guard>} />
          <Route path="/runs" element={<Guard><Runs /></Guard>} />
          <Route path="/runs/:id" element={<Guard><Runs /></Guard>} />
          <Route path="/analytics" element={<Guard><Analytics /></Guard>} />
          <Route path="/settings" element={<Guard><Settings /></Guard>} />
          <Route path="*" element={<Navigate to={me ? "/inbox" : "/login"} />} />
        </Routes>
      </BrowserRouter>
    </MeCtx.Provider>
  );
}
