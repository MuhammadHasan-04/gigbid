#!/usr/bin/env bash
# Re-run every committed evaluation for the active MODEL_PROFILE (needs GigSim on :8081 with held-out jobs:
#   GIGSIM_INCLUDE_HELDOUT=1 GIGSIM_RPM=100000 GIGSIM_ERROR_RATE=0 uvicorn gigsim.server:app --port 8081)
set -euo pipefail
P=${MODEL_PROFILE:-heuristic}
export MODEL_PROFILE=$P
export PYTHONPATH=$PWD GIGBID__MARKETPLACE__MAX_REQUESTS_PER_MINUTE=100000 TRACE_DIR=${TRACE_DIR:-data/runtime/eval_traces}
PY=${PY:-.venv/bin/python}
LIMIT=${LIMIT:-}   # e.g. LIMIT="--limit-per-persona 30" for rate-limited model endpoints
$PY -m evals.runners.rag_eval --ablate --tag $P
$PY -m evals.runners.rag_eval --variants v0,best --split heldout --tag ${P}_heldout
$PY -m evals.runners.pipeline_eval --tag ${P}_dev $LIMIT
$PY -m evals.runners.pipeline_eval --tag ${P}_dev_nodefence --no-defence $LIMIT
$PY -m evals.runners.pipeline_eval --split heldout --tag ${P}_heldout $LIMIT
for v in v0 v5 v8; do GIGBID__RAG__VARIANT=$v $PY -m evals.runners.pipeline_eval --tag ${P}_dev_rag_$v $LIMIT; done
$PY -m evals.runners.ab_test $LIMIT
$PY -m evals.runners.failure_analysis pipeline_${P}_dev.json
