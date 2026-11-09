# Tools

Agents never call GigSim, Upwork, a database or a file directly. Every capability is an MCP tool with a schema,
an owner and a test. Schemas are snapshotted in `tests/contract/snapshots/`, and CI fails when one changes unintentionally.
Per-agent allowlists are in `agent/mcp_client.py` (`ALLOWLIST`).

| Tool | Server | Read / write | Annotations | Auth |
|---|---|---|---|---|
| `get_case_study` | portfolio (GigBid) | read | destructiveHint=false, idempotentHint=true, openWorldHint=false, readOnlyHint=true | bearer (HTTP) / none (stdio) |
| `list_skills` | portfolio (GigBid) | read | destructiveHint=false, idempotentHint=true, openWorldHint=false, readOnlyHint=true | bearer (HTTP) / none (stdio) |
| `search_evidence` | portfolio (GigBid) | read | destructiveHint=false, idempotentHint=true, openWorldHint=false, readOnlyHint=true | bearer (HTTP) / none (stdio) |
| `create_proposal_draft` | marketplace (GigBid) | write | destructiveHint=false, idempotentHint=true, openWorldHint=true, readOnlyHint=false | bearer + human approval token for writes |
| `get_client_history` | marketplace (GigBid) | read | destructiveHint=false, idempotentHint=true, openWorldHint=true, readOnlyHint=true | bearer + human approval token for writes |
| `get_connects_balance` | marketplace (GigBid) | read | destructiveHint=false, idempotentHint=true, openWorldHint=true, readOnlyHint=true | bearer + human approval token for writes |
| `get_job` | marketplace (GigBid) | read | destructiveHint=false, idempotentHint=true, openWorldHint=true, readOnlyHint=true | bearer + human approval token for writes |
| `get_market_stats` | marketplace (GigBid) | read | destructiveHint=false, idempotentHint=true, openWorldHint=true, readOnlyHint=true | bearer + human approval token for writes |
| `get_thread` | marketplace (GigBid) | read | destructiveHint=false, idempotentHint=true, openWorldHint=true, readOnlyHint=true | bearer + human approval token for writes |
| `list_messages` | marketplace (GigBid) | read | destructiveHint=false, idempotentHint=true, openWorldHint=true, readOnlyHint=true | bearer + human approval token for writes |
| `list_proposals` | marketplace (GigBid) | read | destructiveHint=false, idempotentHint=true, openWorldHint=true, readOnlyHint=true | bearer + human approval token for writes |
| `search_jobs` | marketplace (GigBid) | read | destructiveHint=false, idempotentHint=true, openWorldHint=true, readOnlyHint=true | bearer + human approval token for writes |
| `send_message` | marketplace (GigBid) | write | destructiveHint=true, idempotentHint=true, openWorldHint=true, readOnlyHint=false | bearer + human approval token for writes |
| `submit_proposal` | marketplace (GigBid) | write | destructiveHint=true, idempotentHint=true, openWorldHint=true, readOnlyHint=false | bearer + human approval token for writes |
| `create_email_draft` | workspace (GigBid) | write | destructiveHint=false, idempotentHint=true, openWorldHint=false, readOnlyHint=false | bearer (HTTP) |
| `create_tentative_hold` | workspace (GigBid) | write | destructiveHint=false, idempotentHint=true, openWorldHint=false, readOnlyHint=false | bearer (HTTP) |
| `free_slots` | workspace (GigBid) | read | destructiveHint=false, idempotentHint=true, openWorldHint=false, readOnlyHint=true | bearer (HTTP) |
| `search_repositories`, `get_file_contents` | GitHub MCP (official, third-party) | read | as published by GitHub | GitHub PAT (read-only scope) |
| Upwork job search, job details, proposal drafts, messages | Upwork MCP (official, third-party) | read / write-as-draft | as published by Upwork | OAuth 2.1 per user, tokens Fernet-encrypted at rest |

## Write-tool guarantees (Marketplace)

* **Idempotency key** on every write. Results are stored per `(user, tool, key)` in SQLite (`mcp_servers/common.py::IdempotencyStore`), so a retried call returns the stored result (`idempotent_replay: true`) and never submits twice or spends Connects twice. GigSim enforces the same rule server-side, as a second layer.
* **`dry_run`** returns exactly what would be sent and what it costs, including the Connects balance after. The approval screen shows this preview.
* **Human approval token.** A real write needs an HMAC token over `(kind, target, sha256(content))` that only the approval executor mints after the LangGraph interrupt is resumed with "approve". If the model changes one character, the token no longer matches.
* **Bearer auth** on the HTTP endpoint (`MARKETPLACE_MCP_TOKENS`), a **per-user rate limiter** (40/min, under GigSim's 60/min), and an **append-only, hash-chained audit log** (`data/runtime/audit/marketplace.jsonl`: user, tool, PII-masked arguments, result, trace id).

## Third-party servers: trust rationale

* **GitHub MCP** (`https://api.githubcopilot.com/mcp/`): published and maintained by GitHub. We use it read-only, with a PAT that has only public-repo read scope, and allowlist two tools. Repo text it returns goes into the portfolio index as untrusted data and never becomes instructions.
* **Upwork MCP** (`https://mcp.upwork.com/mcp`): Upwork's official server is the only sanctioned automation route (no scraping, no browser automation). Every write it offers is a draft the user must confirm on Upwork, which matches GigBid's own approval gate. **Status: the adapter is implemented, but it was not exercised against a real account in this repo because no Upwork account was available.**

## Client discipline (A6)

Each call has a timeout (75 s), 2 retries with exponential backoff, and a trace span. A circuit breaker in the GigSim adapter turns
repeated failures into `MarketplaceUnavailable`. The run then becomes `dead_letter` with a Retry button, and the UI shows the
"Marketplace unavailable" banner (`/api/health` is polled every 15 s). Kill the marketplace server and the user sees the banner,
pending approvals stay in Postgres, and Retry resumes from the last checkpoint.

## Tests (A7)

* `tests/contract/test_mcp_contract.py` uses a real in-memory MCP client session (`mcp.shared.memory`) to check schemas, annotations, resources, prompts, approval tokens, idempotent replays and input constraints.
* MCP Inspector screenshots: `docs/images/inspector_*.png`.
* Single agent drafting one grounded proposal for a GigSim job: `tests/integration/test_bid_graph.py::test_crash_and_resume_submits_exactly_once`.

## R&D question A: tool granularity

Runner: `evals/runners/tool_study.py` (40 tasks with known correct calls; 17 fine-grained tools vs 3 coarse tools vs the
shipped 10 with rewritten descriptions). It needs a model endpoint, and results will be written to `evals/results/tool_study.json`.
