# ADR 0002: Approval enforced twice: LangGraph interrupt plus HMAC approval token
**Context:** R4 says nothing leaves without human approval. An interrupt alone protects the graph, but not a tool called some other way.
**Decision:** write tools require an HMAC over (kind, target, sha256(content)) that the non-LLM executor mints only after the interrupt is resumed with approve. LLM agents never have write tools in their allowlist.
**Consequences:** changing one character after approval invalidates the token. The secret must be shared between API/worker and the Marketplace server (`APPROVAL_SECRET`).
