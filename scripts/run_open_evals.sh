#!/usr/bin/env bash
# Model-backed evaluation plan sized for Groq free-tier limits (1,000 requests/day and 8k tokens/min per model).
# Two lanes run in parallel because each model has its own limits:
#   lane A: gpt-oss-20b (cheap nodes) + gpt-oss-120b (writer/critic)   lane B: qwen3.8-27b (second open configuration)
set -uo pipefail
export PYTHONPATH=$PWD GIGBID__MARKETPLACE__MAX_REQUESTS_PER_MINUTE=100000 TRACE_DIR=${TRACE_DIR:-data/runtime/eval_traces}
PY=${PY:-.venv/bin/python}
N=${N:-15}
laneA() {
  MODEL_PROFILE=open $PY -m evals.runners.pipeline_eval --tag open_dev --limit-per-persona $N --concurrency 2 --judge
  MODEL_PROFILE=open $PY -m evals.runners.pipeline_eval --tag open_dev_injection --only-injection --limit-per-persona 6 --concurrency 2
  MODEL_PROFILE=open $PY -m evals.runners.pipeline_eval --tag open_dev_injection_nodefence --only-injection --limit-per-persona 6 --no-defence --concurrency 2
  MODEL_PROFILE=open $PY -m evals.runners.pipeline_eval --split heldout --tag open_heldout --limit-per-persona 10 --concurrency 2
  MODEL_PROFILE=open $PY -m evals.runners.agents_compare --n 24
}
laneB() {
  MODEL_PROFILE=open_qwen $PY -m evals.runners.pipeline_eval --tag open_qwen_dev --limit-per-persona $N --concurrency 2
  MODEL_PROFILE=open_qwen $PY -m evals.runners.tool_study --node writer
  MODEL_PROFILE=open_qwen $PY -m evals.runners.rag_eval --variants v0,v1,v7,best --limit 25 --tag open_qwen
}
laneA > data/runtime/eval_laneA.log 2>&1 &
laneB > data/runtime/eval_laneB.log 2>&1 &
wait
echo ALL_DONE
