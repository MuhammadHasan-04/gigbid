import type { ReactNode } from "react";
import { errorText } from "../lib/api/client";

export function Badge({ tone = "neutral", children, title }: { tone?: "good" | "warn" | "bad" | "neutral" | "info"; children: ReactNode; title?: string }) {
  return <span className={`badge badge-${tone}`} title={title}>{children}</span>;
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <div className="state" role="status" aria-live="polite"><span className="spinner" aria-hidden /> {label}</div>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="state empty"><strong>{title}</strong>{children && <div className="muted">{children}</div>}</div>;
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const msg = errorText(error);
  return (
    <div className="state error" role="alert">
      <strong>Couldn’t load this.</strong> <span>{String(msg)}</span>
      {onRetry && <button className="btn small" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function Score({ value, invert = false, label }: { value?: number | null; invert?: boolean; label: string }) {
  if (value === null || value === undefined) return <span className="muted">–</span>;
  const good = invert ? value < 0.35 : value >= 0.7;
  const bad = invert ? value > 0.6 : value < 0.45;
  return <Badge tone={good ? "good" : bad ? "bad" : "warn"} title={label}>{label} {value.toFixed(2)}</Badge>;
}

export function actionTone(a?: string | null): "good" | "bad" | "warn" | "neutral" {
  return a === "bid" ? "good" : a === "skip" ? "bad" : a === "watch" ? "warn" : "neutral";
}
