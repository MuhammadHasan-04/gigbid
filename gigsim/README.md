# GigSim (student-built stand-in)

The instructor's GigSim package was not available while this repository was being built, so
this folder contains a **stand-in** that implements the behaviour the assignment describes:

| Feature | Where |
|---|---|
| Jobs with client histories, Connects, proposals, messages | `server.py` |
| Bearer auth, per-token rate limit (429 + Retry-After), random 503s | `server.py` middleware |
| Simulated clients with hidden preferences + reply/interview/hire decision | `client_model.py` |
| 3 personas (CV PDF, 22 case studies, repos with README+code, reviews, 150 labelled past proposals) | `generate.py` → `data/personas/` |
| 1,500 historical jobs for pricing, 600 dev jobs with gold labels, 158-job live stream with duplicates, scams, injected instructions | `generate.py` → `data/gigsim/`, `evals/datasets/` |
| Policy pack v1 and the v2 "platform policy update" | `data/policy_pack/` |

Regenerate deterministically: `python -m gigsim.generate --heldout`.
Run: `uvicorn gigsim.server:app --port 8081`.

If the official GigSim is supplied, replace this folder and point `GIGSIM_BASE_URL` at it. Only
`mcp_servers/marketplace/adapters/gigsim.py` talks to this API, so nothing else changes.
