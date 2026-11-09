# GigBid developer commands. `make help` lists them.
PY ?= .venv/bin/python
export PYTHONPATH := $(CURDIR)
EVAL_ENV = MODEL_PROFILE=$${MODEL_PROFILE:-heuristic} GIGBID__MARKETPLACE__MAX_REQUESTS_PER_MINUTE=100000 TRACE_DIR=data/runtime/eval_traces

.PHONY: help setup seed dev up down test unit contract integration e2e eval eval-rag eval-pipeline eval-heldout smoke lint api-client web demo reset

help:
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'

setup: ## create venv and install pinned deps + web deps
	uv venv -p 3.12 .venv && uv pip install -e ".[dev]" && cd apps/web && npm ci

seed: ## regenerate the GigSim world (personas, jobs, dev set, held-out set)
	$(PY) -m gigsim.generate --heldout

dev: ## run gigsim + api (inline worker) + web dev server locally
	(GIGSIM_RPM=600 $(PY) -m uvicorn gigsim.server:app --port 8081 &) ; \
	(RUN_INLINE=1 $(PY) -m uvicorn apps.api.main:app --port 8000 --reload &) ; \
	cd apps/web && npm run dev

up: ## docker compose up (everything)
	docker compose -f infra/docker-compose.yml --env-file .env up --build

down:
	docker compose -f infra/docker-compose.yml down

test: unit contract integration ## all python tests

unit:
	$(PY) -m pytest -q tests/unit

contract: ## MCP tool contracts + schema snapshots
	$(PY) -m pytest -q tests/contract

integration:
	$(PY) -m pytest -q tests/integration

e2e: ## Playwright UI tests (needs the API on :8000 serving the built web app)
	cd apps/web && npx playwright test

eval: eval-rag eval-pipeline ## retrieval + decision + GigSim reply-rate evals -> evals/results/*.json

eval-rag:
	$(EVAL_ENV) $(PY) -m evals.runners.rag_eval --ablate --tag $${MODEL_PROFILE:-heuristic}

eval-pipeline:
	$(EVAL_ENV) $(PY) -m evals.runners.pipeline_eval --tag $${MODEL_PROFILE:-heuristic}_dev

eval-heldout:
	$(EVAL_ENV) GIGSIM_INCLUDE_HELDOUT=1 $(PY) -m evals.runners.pipeline_eval --split heldout --tag $${MODEL_PROFILE:-heuristic}_heldout

smoke: ## 30-job smoke eval with CI thresholds
	$(EVAL_ENV) $(PY) -m evals.runners.pipeline_eval --limit-per-persona 10 --tag smoke && $(PY) -m evals.runners.check_thresholds evals/results/pipeline_smoke.json

lint:
	$(PY) -m ruff check agent rag mcp_servers apps/api worker evals tests

api-client: ## regenerate the TypeScript client from FastAPI's OpenAPI schema
	$(PY) -m apps.api.export_openapi apps/web/openapi.json && cd apps/web && npx openapi-typescript openapi.json -o src/lib/api/schema.d.ts

web:
	cd apps/web && npm run build

demo: ## seed a reviewer account and scout once
	REVIEWER_EMAIL=$${REVIEWER_EMAIL:-reviewer@gigbid.dev} REVIEWER_PASSWORD=$${REVIEWER_PASSWORD:?set REVIEWER_PASSWORD} $(PY) -m scripts.demo

reset:
	./scripts/reset_dev.sh
