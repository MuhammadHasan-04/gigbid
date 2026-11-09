// Renders proposal text; every [E:id] citation becomes a focusable chip that shows the evidence on hover/focus.
import { useId, useState } from "react";

const CITE = /\[E:([^\]]+)\]/g;

export function EvidenceText({ text, evidence, claims }: { text: string; evidence: Record<string, string>; claims?: { text: string; verdict: string; reason?: string }[] }) {
  const sentences = text.split(/(?<=[.!?])\s+/);
  return (
    <div className="evidence-text" data-testid="evidence-text">
      {sentences.map((s, i) => {
        const claim = claims?.find((c) => c.text.trim() === s.trim());
        const parts: (string | { id: string })[] = [];
        let last = 0;
        for (const m of s.matchAll(CITE)) {
          parts.push(s.slice(last, m.index));
          m[1].split(",").forEach((id) => parts.push({ id: id.trim() }));
          last = (m.index ?? 0) + m[0].length;
        }
        parts.push(s.slice(last));
        return (
          <span key={i} className={`sent ${claim ? "claim-" + claim.verdict : ""}`} title={claim ? `${claim.verdict}: ${claim.reason ?? ""}` : undefined}>
            {parts.map((p, j) => typeof p === "string" ? <span key={j}>{p}</span> : <Cite key={j} id={p.id} text={evidence[p.id]} />)}{" "}
          </span>
        );
      })}
    </div>
  );
}

function Cite({ id, text }: { id: string; text?: string }) {
  const [open, setOpen] = useState(false);
  const tid = useId();
  return (
    <span className="cite-wrap">
      <button type="button" className={`cite ${text ? "" : "cite-missing"}`} aria-describedby={tid} data-testid="cite"
        onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}>
        {id.split(":").slice(1).join(":")}
      </button>
      {open && <span role="tooltip" id={tid} className="cite-pop"><strong>{id}</strong><br />{text ?? "Evidence not in this draft's evidence set."}</span>}
    </span>
  );
}
