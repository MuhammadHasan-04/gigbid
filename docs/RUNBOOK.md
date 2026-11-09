# Runbook

## Services

| Service | Port | Health |
|---|---|---|
| web (nginx) | 8080 | `/` |
| api | 8000 | `/api/health` (marketplace status, model profile, policy version) |
| worker (Arq) | – | `arq --check worker.main.WorkerSettings` |
| mcp-portfolio / mcp-marketplace / mcp-workspace | 8101 / 8102 / 8103 | `/health` |
| gigsim | 8081 | `/health` |
| postgres (pgvector) / redis / ollama | 5432 / 6379 / 11434 | compose healthchecks |

## Schedules and polling policy (E1)

* The worker `tick` runs every minute. It enqueues `scout_job` for a user when their interval has elapsed, and `sync_job` every 5 minutes.
* **GigSim**: each saved search runs every `every_minutes` (default 30, minimum 15).
* **Upwork live mode**: the interval is at least `marketplace.live_poll_interval_minutes` = **240 minutes**. Why: a freelancer
  reacting within a few hours keeps most of the early-proposal advantage, and 6 searches a day per saved search is in line with a
  person checking the feed manually, not a bot. Polling faster would look like scraping, which Upwork's automation guidance forbids.
  Reads go only through the official MCP server. There is no scraping, no browser automation and no session cookies.
* Arq job ids are deterministic (`analyse:{user}:{job}`, `scout:{user}:{minute}`), so double enqueues run once. `tasks.analyse`
  skips jobs whose thread already exists, so a worker restart never double-analyses. Resumes reuse the checkpoint and idempotency keys, so a restart never double-submits.

## Deploy (single container + managed Postgres)

The public deployment runs the API image with `RUN_INLINE=1` (background work as asyncio tasks in the API process),
`MCP_TRANSPORT=inproc`, GigSim as a second process, and a managed Postgres (Neon). The model profile is `open` (Groq, free tier).
Secrets are set in the host's secret store only. `.env` is never committed.

## Common incidents

* **Marketplace down**: the banner shows, runs go to `dead_letter`, and pending approvals are safe in Postgres. When GigSim is back, use Retry in the inbox (or `POST /api/jobs/{id}/retry`).
* **Model provider rate-limited**: `agent/llm.py` retries 429/5xx with Retry-After, then uses the profile's fallback model, then the heuristic rules (visible as `provider=heuristic` in the trace).
* **A proposal approved but the worker crashed**: resume the thread (`Retry`). The submit node re-runs with the same idempotency keys and GigSim returns `idempotent_replay`.
* **Reset the dev environment**: `make reset`.

## Change request procedure

The policy pack is versioned data (`data/policy_pack/policy_v{N}.yaml`), and `policy.version` in `agent/config.yaml` selects it.
New regex rules and Connects surcharges need no code. Record the diff in `evals/results/change_request.json`.
