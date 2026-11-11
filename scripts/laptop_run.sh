#!/usr/bin/env bash
# =====================================================================================
# GigBid: run the remaining model experiments on your own laptop (Git Bash, WSL or Linux/macOS).
#
#   ./scripts/laptop_run.sh setup          # once: venv + deps + GigSim world (incl. held-out set) + .env check
#   ./scripts/laptop_run.sh dev            # 30 practice jobs on gpt-oss (+ injection test with/without defences)
#   ./scripts/laptop_run.sh judge-export   # writes evals/datasets/judge_labels.csv  -> YOU fill human_score (1-5)
#   ./scripts/laptop_run.sh judge-score    # Cohen's kappa between your scores and the LLM judge
#   ./scripts/laptop_run.sh heldout        # held-out run (15 jobs)
#   ./scripts/laptop_run.sh compare        # single agent vs supervisor vs graph (R&D question C)
#   ./scripts/laptop_run.sh real           # the agents on 60 REAL Upwork posts (Kaggle) with gpt-oss
#   ./scripts/laptop_run.sh results        # regenerate README results block + report PDF inputs
#   ./scripts/laptop_run.sh push           # commit evals/results + README and push to GitHub
#   ./scripts/laptop_run.sh all            # dev -> heldout -> compare -> results (no judge steps)
#
# Groq free tier = 200,000 tokens per day PER MODEL. If a step stops with "daily quota exhausted",
# just run the same step again later: finished model calls are cached (LLM_CACHE=1) and cost nothing,
# and jobs that fell back to rules are excluded from the results (--require-model).
# =====================================================================================
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

# ---- python inside the venv (Windows Git Bash uses Scripts/, everything else bin/)
if [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe; else PY=.venv/bin/python; fi

export PYTHONPATH="$ROOT" LLM_CACHE=1 PYTHONIOENCODING=utf-8 \
       GIGBID__MARKETPLACE__MAX_REQUESTS_PER_MINUTE=100000 GIGBID_NODE_TIMEOUT_SCALE=4 \
       TRACE_DIR="$ROOT/data/runtime/eval_traces" GIGSIM_BASE_URL=http://127.0.0.1:8081
mkdir -p data/runtime evals/results
LOG="data/runtime/laptop_$(date +%Y%m%d_%H%M%S).log"

say() { printf '\n\033[1;32m== %s\033[0m\n' "$*" | tee -a "$LOG"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" | tee -a "$LOG"; exit 1; }

need_env() {
  [ -f .env ] || die ".env missing. Create it with one line:  GROQ_API_KEY=gsk_...   (see .env.example)"
  grep -q '^GROQ_API_KEY=gsk_' .env || die ".env has no GROQ_API_KEY=gsk_... line"
  grep -q '^MODEL_PROFILE=' .env || echo "MODEL_PROFILE=open" >> .env
}

check_model() {
  say "Checking that Groq answers (key in .env)"
  MODEL_PROFILE=open $PY scripts/check_models.py 2>&1 | grep -v "HTTP Request" | tee -a "$LOG"
  MODEL_PROFILE=open $PY scripts/check_models.py 2>&1 | grep -q "test call OK" || die "Groq test call failed (see above)"
}

start_gigsim() {
  if curl -fs http://127.0.0.1:8081/health >/dev/null 2>&1; then return; fi
  say "Starting GigSim (with held-out jobs) on :8081"
  GIGSIM_INCLUDE_HELDOUT=1 GIGSIM_REAL_JOBS=1 GIGSIM_RPM=100000 GIGSIM_ERROR_RATE=0 GIGSIM_POLICY_VERSION=2 \
    GIGSIM_STATE_FILE="$ROOT/data/runtime/eval_gigsim_state.json" \
    nohup $PY -m uvicorn gigsim.server:app --host 127.0.0.1 --port 8081 > data/runtime/gigsim.log 2>&1 &
  for _ in $(seq 1 30); do curl -fs http://127.0.0.1:8081/health >/dev/null 2>&1 && return; sleep 1; done
  die "GigSim did not start (see data/runtime/gigsim.log)"
}

run() {  # run <title> <command...> ; logs everything, never aborts the whole script
  say "$1"; shift
  "$@" 2>&1 | grep -v "HTTP Request" | tee -a "$LOG"
  return "${PIPESTATUS[0]}"
}

summary() {
  $PY - <<'EOF'
import json, glob, os
for f in sorted(glob.glob("evals/results/pipeline_open*.json")):
    d = json.load(open(f)); o = d["overall"].get("overall")
    if o is None:  # the real-posts run has no gold labels
        continue
    print(f"{os.path.basename(f):45s} jobs={o['n_jobs']:3d} excluded={len(d.get('excluded_quota_fallback', [])):3d} "
          f"F1={o['bid_f1']} props={o['n_proposals']} reply={o['gigsim_reply_rate']} inj_success={o['injection_attack_success_rate']}")
for name in ("agents_compare.json", "judge_calibration.json", "tool_study.json", "pipeline_open_real.json"):
    p = f"evals/results/{name}"
    print(name, "OK" if os.path.exists(p) else "not yet")
EOF
}

cmd_setup() {
  say "Python environment"
  command -v python3 >/dev/null || command -v python >/dev/null || die "Install Python 3.12 first (python.org)"
  PYBIN=$(command -v python3 || command -v python)
  if ! [ -x .venv/bin/python ] && ! [ -x .venv/Scripts/python.exe ]; then
    if command -v uv >/dev/null; then uv venv -p 3.12 .venv; else "$PYBIN" -m venv .venv; fi
  fi
  if [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe; else PY=.venv/bin/python; fi
  $PY -m pip install -q --upgrade pip
  $PY -m pip install -q -e ".[dev]" || die "pip install failed"
  say "Generating the GigSim world incl. the git-ignored held-out set (deterministic, same as the repo)"
  $PY -m gigsim.generate --heldout | tee -a "$LOG"
  git status --porcelain data evals/datasets | head -5
  need_env
  check_model
  say "Setup done. Next:  ./scripts/laptop_run.sh dev"
}

cmd_dev() {
  need_env; start_gigsim
  run "1/3 Practice run: 30 dev jobs (10 per persona) on gpt-oss-20b + gpt-oss-120b, with LLM judge" \
    env MODEL_PROFILE=open $PY -m evals.runners.pipeline_eval --tag open_dev --limit-per-persona 10 --concurrency 1 --judge --require-model
  run "2/3 Injection test WITH defences (9 planted-injection jobs)" \
    env MODEL_PROFILE=open $PY -m evals.runners.pipeline_eval --tag open_dev_injection --only-injection --limit-per-persona 3 --concurrency 1 --require-model
  run "3/3 Injection test WITHOUT defences (same 9 jobs)" \
    env MODEL_PROFILE=open $PY -m evals.runners.pipeline_eval --tag open_dev_injection_nodefence --only-injection --limit-per-persona 3 --no-defence --concurrency 1 --require-model
  summary
}

cmd_heldout() {
  need_env; start_gigsim
  run "Held-out run: 15 jobs (5 per persona), never used for tuning" \
    env MODEL_PROFILE=open GIGSIM_INCLUDE_HELDOUT=1 $PY -m evals.runners.pipeline_eval --split heldout --tag open_heldout --limit-per-persona 5 --concurrency 1 --require-model
  run "Second open model (qwen3.8-27b) on the same 30 dev jobs, for the model comparison" \
    env MODEL_PROFILE=open_qwen $PY -m evals.runners.pipeline_eval --tag open_qwen_dev --limit-per-persona 10 --concurrency 1 --require-model
  summary
}

cmd_compare() {
  need_env; start_gigsim
  [ -f evals/results/pipeline_open_dev.json ] || die "run './scripts/laptop_run.sh dev' first (the graph's results are the baseline)"
  run "R&D C: single ReAct agent vs langgraph-supervisor vs the GigBid graph on the same 9 jobs (gpt-oss-120b)" \
    env MODEL_PROFILE=open $PY -m evals.runners.agents_compare --n 9 --graph-tag open_dev
  summary
}

cmd_real() {
  need_env; start_gigsim
  curl -fs http://127.0.0.1:8081/health | grep -q '"real_jobs":[1-9]' || die "GigSim is running without real jobs: stop it (it was started outside this script) and rerun"
  run "Real Upwork posts (Kaggle): 60 posts, 20 per persona, on gpt-oss (no gold labels; see docs/DATA_CARD.md)" \
    env MODEL_PROFILE=open $PY -m evals.runners.real_data_eval pipeline --tag open_real --concurrency 1
  summary
}

cmd_judge_export() {
  [ -f evals/results/pipeline_open_dev.json ] || die "run './scripts/laptop_run.sh dev' first"
  $PY - <<'EOF'
import csv, json, random
from evals.runners.common import load_jobs
rows = [r for r in json.load(open("evals/results/pipeline_open_dev.json"))["rows"] if r.get("cover_letter")]
extra = []
for f in ("evals/results/pipeline_open_qwen_dev.json", "evals/results/pipeline_heuristic_dev.json"):
    try:
        extra += [r for r in json.load(open(f))["rows"] if r.get("cover_letter")]
    except FileNotFoundError:
        pass
random.Random(30).shuffle(extra)
items = (rows + extra)[:30]   # model proposals first; topped up to 30 from other runs
random.Random(7).shuffle(items)
jobs = load_jobs()
with open("evals/datasets/judge_labels.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["item", "job_id", "job_title", "job_description", "proposal", "human_score"])
    for i, r in enumerate(items):
        j = jobs[r["job_id"]]
        w.writerow([i, r["job_id"], j["title"], j["description"][:600], r["cover_letter"], ""])
print(f"wrote evals/datasets/judge_labels.csv with {len(items)} proposals ({len(rows)} from the gpt-oss run)")
EOF
  cat <<'EOF'

NOW YOU: open evals/datasets/judge_labels.csv in Excel and fill the human_score column (1-5) for every row:
  5 = specific to this client, every claim backed by named past work, concise, clear next step
  4 = specific and grounded, minor padding
  3 = relevant but partly generic, or one weak claim
  2 = mostly generic, or an unsupported claim
  1 = generic template, made-up experience, or a policy violation (contact details, guarantees)
Score from your own reading; do not look at any model scores. Save as CSV (keep the same file name), then run:
  ./scripts/laptop_run.sh judge-score
EOF
}

cmd_judge_score() {
  need_env
  run "Judge calibration: Cohen's kappa between your 30 scores and the LLM judge (gpt-oss-120b)" \
    env MODEL_PROFILE=open $PY -m evals.runners.judge_calibration score
}

cmd_results() {
  run "Regenerating the README results block from evals/results" $PY scripts/update_readme.py heuristic
  $PY scripts/check_readme_numbers.py | tee -a "$LOG"
  if command -v node >/dev/null && node -e "require('playwright')" 2>/dev/null; then
    run "Rebuilding the report PDF" $PY docs/report/build_report.py heuristic
  else
    echo "(report PDF not rebuilt here: needs node + playwright; the results files are what matter)"
  fi
  summary
}

cmd_push() {
  say "Committing results and pushing to GitHub"
  git add evals/results evals/datasets/judge_labels.csv evals/datasets/tool_tasks.jsonl README.md docs 2>/dev/null
  git -c user.name="Hasan" -c user.email="${GIT_EMAIL:-ha7971768@gmail.com}" commit -m "Model-backed evaluation runs (Groq gpt-oss / qwen): dev, injection, held-out, agent comparison, judge calibration" || echo "nothing to commit"
  git push origin HEAD:main || die "git push failed: sign in to GitHub when asked, or set a token remote"
}

case "${1:-help}" in
  setup) cmd_setup ;;
  dev) cmd_dev ;;
  heldout) cmd_heldout ;;
  compare) cmd_compare ;;
  real) cmd_real ;;
  judge-export) cmd_judge_export ;;
  judge-score) cmd_judge_score ;;
  results) cmd_results ;;
  push) cmd_push ;;
  summary) summary ;;
  all) cmd_dev; cmd_heldout; cmd_compare; cmd_real; cmd_results ;;
  *) sed -n '2,20p' "$0" ;;
esac
