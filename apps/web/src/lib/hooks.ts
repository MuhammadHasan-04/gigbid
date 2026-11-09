import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, getToken } from "./api/client";

export function useLoad<T>(fn: () => Promise<{ data?: T; error?: unknown }>, deps: unknown[] = [], pollMs?: number) {
  const [data, setData] = useState<T | undefined>();
  const [error, setError] = useState<unknown>();
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    try {
      const r = await fn();
      if (r.error) setError(r.error); else { setData(r.data); setError(undefined); }
    } catch (e) { setError(String(e)); }
    setLoading(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { setLoading(true); reload(); }, [reload]);
  useEffect(() => {
    if (!pollMs) return;
    const t = setInterval(reload, pollMs);
    return () => clearInterval(t);
  }, [reload, pollMs]);
  return { data, error, loading, reload, setData };
}

export type RunEvent = { type: string; node?: string; status?: string | null; log?: { msg?: string; latency_s?: number; tokens?: number; providers?: string[] }; payload?: unknown; trace_id?: string; error?: string; degraded?: boolean; next?: string[]; attention_reason?: string | null };

/** Live node-by-node progress over Server-Sent Events. */
export function useRunStream(threadId: string | null | undefined) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const es = useRef<EventSource | null>(null);
  useEffect(() => {
    setEvents([]);
    if (!threadId) return;
    const url = `${API_BASE}/api/runs/stream?thread_id=${encodeURIComponent(threadId)}&token=${encodeURIComponent(getToken() ?? "")}`;
    const src = new EventSource(url);
    es.current = src;
    src.onopen = () => setConnected(true);
    src.onerror = () => setConnected(false);
    src.addEventListener("run", (m) => {
      try { setEvents((prev) => [...prev, JSON.parse((m as MessageEvent).data)]); } catch { /* ignore */ }
    });
    return () => src.close();
  }, [threadId]);
  return { events, connected };
}
