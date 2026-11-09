# Architecture

```
 Browser (React, TS client generated from OpenAPI)
   │  REST + Server-Sent Events          x-trace-id flows end to end
 FastAPI (apps/api) ── Postgres: users, jobs_seen, run_events, pipeline, LangGraph checkpoints + store
   │  enqueue                               │
 Arq worker (worker/) on Redis ── LangGraph runtime (agent/runtime.py)
   │                                         ├── bid graph (one thread per job)
   │                                         └── conversation graph (one thread per client conversation)
   │  MCP (Streamable HTTP, bearer)        per-agent tool allowlists, timeouts, retries
   ├── Portfolio MCP (read)   ── rag/ (hybrid retrieval, verifier)  ←─ GitHub MCP (repo ingestion)
   ├── Marketplace MCP (read+write) ── marketplace port ── GigSim adapter | Upwork-live adapter → Upwork MCP (OAuth 2.1)
   └── Workspace MCP (calendar slots, holds, email drafts)
```

Diagrams rendered from code: `docs/images/bid_graph.png`, `docs/images/conversation_graph.png` (`graph.get_graph().draw_mermaid()`).

## Why each agent exists

| Agent | Why it is separate | Model tier (config) | MCP |
|---|---|---|---|
| Scout | Cheap, scheduled and idempotent. Never needs a model to dedupe | small | marketplace read |
| Job Analyst | Turns messy prose into a typed `JobSpec`. Has no tool access, so an injected post cannot make it call anything | small | none |
| Risk Assessor | Rule floor (regex scam/injection signals) plus model judgement plus client history. Rules can't be overruled downward | small | marketplace read |
| Fit Matcher | One retrieval per requirement, so a requirement with no evidence becomes an explicit "will not be claimed" | small | portfolio read |
| Pricing Strategist | Numbers are computed. The model only writes the rationale. Can veto a bid (floor > budget, Connects not worth it) | small | marketplace read |
| Proposal Writer | The only free-text generator; strongest model | large | portfolio read |
| Verifier (claim split + check) | Deterministic entity check first (skills, numbers, names), model only for claims without entities | small | portfolio read |
| Critic | Sends back at most twice (`budgets.max_revisions`) | large | portfolio read |
| Compliance Guard | Policy pack is data (`data/policy_pack/policy_v*.yaml`). Blocks with a reason shown in the UI | none (rules) | none |
| Client Liaison | Intent classification, replies, interview slots; same approval gate | large | marketplace read/write-after-approval, workspace |

Analyst, Risk and Fit run in parallel with `Send`. Fit can't wait for the Analyst's requirements, so it uses the cheap
rule extractor, and `decide` tops up any requirement the Analyst found that Fit missed. This is a deliberate trade:
wall-clock parallelism in exchange for one extra (cheap) retrieval in a minority of jobs.

## State, trace, memory (kept apart)

* **State** (`agent/state.py`): typed fields for this job right now (job, job_spec, risk, fit, evidence, decision, price, draft, critiques, compliance, approval, submission) with reducers where parallel branches write (`evidence` merge, `log`/`errors` append, `steps`/`tokens`/`usd` add).
* **Execution trace** (`agent/tracing.py`): every model call, tool name, argument, result preview, latency, tokens and USD, PII-masked, keyed by trace id. Shown in the Agent run viewer and mirrored to Langfuse when keys are set.
* **Long-term memory** (`agent/memory`): LangGraph `PostgresStore`, namespaces per user. Only `promotion_rules.py` writes. Style rules are promoted after 2 distinct edited jobs show the same pattern. Outcome memory takes counts only from marketplace status events, and exemplars only from replied proposals once a category has 3 or more sends.

## Durability and failure handling

* `AsyncPostgresSaver` checkpoints every superstep. The approval interrupt is just a checkpoint, so you can kill the API, restart it and approve, and the graph resumes at `approval`.
* `submit` runs after the human decision with idempotency keys `sha256(user|job|draft)` / `sha256(user|job|submit)`. Replaying it from the previous checkpoint (crash after the HTTP call) returns `idempotent_replay: true`, which is tested in `tests/integration`.
* Per-node `RetryPolicy` (2 attempts, backoff) on transient errors, per-node timeouts, fallback model per profile, and heuristic last resort. Repeated marketplace failure → `dead_letter` + Retry. Step or token budget exceeded → `needs_attention`.

## The marketplace port (R1)

`agent/marketplace_port.py` defines the interface. `mcp_servers/marketplace/adapters/{gigsim,upwork_live}.py` implement it.
`marketplace.mode` in config picks one. Only the Marketplace MCP server holds an adapter, so the graph code is
identical in both modes. Switching to live changes one config value plus the OAuth connection in Settings. The Upwork
adapter maps tools by name (`UPWORK_TOOL_MAP`, overridable in config), and its `submit_proposal` returns
`awaiting_platform_confirmation`.
