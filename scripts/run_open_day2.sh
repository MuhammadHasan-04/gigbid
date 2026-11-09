#!/usr/bin/env bash
# Day-2 model runs on Groq free tier (each model: 200k tokens/day). Cached prompts cost nothing on re-runs.
set -uo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=$PWD LLM_CACHE=1 GIGBID__MARKETPLACE__MAX_REQUESTS_PER_MINUTE=100000 GIGBID_NODE_TIMEOUT_SCALE=4 TRACE_DIR=data/runtime/eval_traces
PY=.venv/bin/python
pgrep -f "gigsim.server" >/dev/null || (GIGSIM_INCLUDE_HELDOUT=1 GIGSIM_RPM=100000 GIGSIM_ERROR_RATE=0 GIGSIM_POLICY_VERSION=2 GIGSIM_STATE_FILE=/tmp/evalstate.json nohup $PY -m uvicorn gigsim.server:app --port 8081 > /tmp/gs.log 2>&1 &) ; sleep 4
( MODEL_PROFILE=open $PY -m evals.runners.pipeline_eval --tag open_dev --limit-per-persona 10 --concurrency 1 --judge --require-model
  MODEL_PROFILE=open $PY -m evals.runners.pipeline_eval --tag open_dev_injection --only-injection --limit-per-persona 3 --concurrency 1 --require-model
  MODEL_PROFILE=open $PY -m evals.runners.pipeline_eval --tag open_dev_injection_nodefence --only-injection --limit-per-persona 3 --no-defence --concurrency 1 --require-model
) > data/runtime/day2_laneA.log 2>&1 &
( MODEL_PROFILE=open_qwen $PY -m evals.runners.pipeline_eval --tag open_qwen_dev --limit-per-persona 10 --concurrency 1 --require-model
) > data/runtime/day2_laneB.log 2>&1 &
wait
grep -hE "^\[" data/runtime/day2_lane*.log
