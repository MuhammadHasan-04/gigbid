# AI usage

**Tool:** Claude (Anthropic) working as a coding agent in a cloud workspace, directed by me (Hasan).

**What it was used for:** scaffolding and implementing most of the Python (GigSim stand-in generator and API, MCP servers,
RAG variants, verifier, LangGraph nodes and graphs, FastAPI, worker), the React UI, tests, CI, Docker files, eval runners
and first drafts of the docs and report. I reviewed the design decisions and results and am accountable for every line.

**Files:** essentially all of `agent/`, `rag/`, `mcp_servers/`, `gigsim/`, `apps/`, `worker/`, `evals/runners/`, `tests/`, `infra/`, `docs/`.

**Things it got wrong that were caught:**
1. The trace PII masker redacted every key containing "token", which turned `tokens_in` into `"[REDACTED]"` and crashed the cost summary. Caught by the first API run and fixed to an explicit secret-key list (`agent/tracing.py`).
2. A module named `apps/api/queue.py` shadowed Python's stdlib `queue` when a script ran from that folder (`urllib3` crashed). Renamed to `jobqueue.py`.
3. The claim verifier treated "LLM" in "LLM fine-tuning" as a client name, and stripping skill names with a plain substring regex deleted the "r" from "Cedar" (the skill `R`). It now strips with the word-boundary skill patterns (`rag/verify.py::entities`), covered by `tests/unit/test_verify.py`.
4. The Pricing Strategist proposed bids above the client's budget when the user's floor was higher. It now vetoes the bid with a reason instead.
5. Sync MCP tools blocked the API event loop during GigSim rate-limit backoff. Tool calls now run in a worker thread.

**What I verified myself:** the crash-and-resume behaviour, approval gating, the numbers in README against `evals/results/`,
and the judge-calibration labels (which must be my own, see `evals/datasets/judge_labels.csv`).
