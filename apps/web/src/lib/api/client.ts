// Typed client generated from FastAPI's OpenAPI schema (schema.d.ts is generated: `npm run gen:api`; do not hand-edit it).
import createClient, { type Middleware } from "openapi-fetch";
import type { paths, components } from "./schema";

export type Schemas = components["schemas"];
export const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "";

export function getToken(): string | null {
  try { return localStorage.getItem("gigbid_token"); } catch { return null; }
}
export function setToken(t: string | null) {
  try { if (t) localStorage.setItem("gigbid_token", t); else localStorage.removeItem("gigbid_token"); } catch { /* storage unavailable */ }
}

const auth: Middleware = {
  async onRequest({ request }) {
    const t = getToken();
    if (t) request.headers.set("Authorization", `Bearer ${t}`);
    request.headers.set("x-trace-id", "tr-" + crypto.randomUUID().replace(/-/g, "").slice(0, 16));
    return request;
  },
  async onResponse({ response }) {
    if (response.status === 401 && !location.pathname.startsWith("/login")) {
      setToken(null);
      location.assign("/login");
    }
    return response;
  },
};

export const api = createClient<paths>({ baseUrl: API_BASE });
api.use(auth);

export function errorText(e: unknown): string {
  if (!e) return "Something went wrong";
  if (typeof e === "string") {
    // a proxy error page (e.g. the host's 502 while the server restarts) arrives as raw HTML
    if (/^\s*</.test(e) || /<html/i.test(e)) {
      return /502|503|504|Bad Gateway/i.test(e)
        ? "The server is restarting or waking up (free hosting sleeps when idle). Wait about a minute, then try again."
        : "The server returned an unexpected page. Try again in a minute.";
    }
    return e.length > 300 ? e.slice(0, 300) + "…" : e;
  }
  const d = (e as { detail?: unknown }).detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x: { msg?: string }) => x.msg).join("; ");
  return "Request failed";
}
