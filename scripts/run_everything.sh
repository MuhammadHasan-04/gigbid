#!/usr/bin/env bash
# =====================================================================================
# GigBid: everything that is left, in one go (called by RUN_EVERYTHING.bat on Windows).
#
#   setup -> 30 practice jobs on gpt-oss (+ LLM judge, + injection test with / without defences)
#   -> held-out run -> single agent vs supervisor vs graph -> real Upwork posts
#   -> your 30 judge scores (the only manual step; you can skip it) -> qwen comparison
#   -> README results -> commit + push -> gigbid_source.zip
#
# Safe to run again: finished model calls are cached (LLM_CACHE=1), so a rerun only does what is missing.
# Groq free tier = 200k tokens per day per model. If the day's quota runs out, the script carries on with
# the other steps, then tells you what to rerun tomorrow.
# =====================================================================================
set -uo pipefail
cd "$(dirname "$0")/.."
R=./scripts/laptop_run.sh
chmod +x "$R" 2>/dev/null || true
if [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe; else PY=.venv/bin/python; fi

hdr() { printf '\n\033[1;36m################ %s ################\033[0m\n' "$*"; }
ok_file() { [ -f "evals/results/$1" ]; }

hdr "0/8  Setup (venv, packages, simulator data, Groq check)"
bash "$R" setup || { echo "Setup failed: read the message above, fix it, and run again."; exit 1; }
if [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe; else PY=.venv/bin/python; fi

hdr "1/8  Practice run: 30 dev jobs + injection tests"
bash "$R" dev

hdr "2/8  Held-out run (15 jobs never used for tuning)"
bash "$R" heldout

hdr "3/8  R&D C: single agent vs supervisor vs graph"
ok_file pipeline_open_dev.json && bash "$R" compare || echo "skipped: needs the practice run first"

hdr "4/8  Real Upwork posts (Kaggle)"
bash "$R" real

hdr "5/8  Judge calibration (your 30 scores)"
if ok_file judge_calibration.json; then
  echo "already done"
elif ok_file pipeline_open_dev.json; then
  if ! grep -qE ',[1-5]\s*$' evals/datasets/judge_labels.csv 2>/dev/null; then
    bash "$R" judge-export
    if command -v cmd.exe >/dev/null 2>&1; then cmd.exe //c start "" "evals\\datasets\\judge_labels.csv" >/dev/null 2>&1 || true; fi
    echo
    echo "The file evals/datasets/judge_labels.csv is open (or open it in Excel yourself)."
    echo "Fill the human_score column (1-5) for every row from your own reading, save as CSV with the same name."
    read -r -p "Press Enter when saved, or type s and Enter to skip this step: " ans
  else
    ans=""
  fi
  if [ "${ans:-}" != "s" ]; then bash "$R" judge-score; else echo "skipped (run ./scripts/laptop_run.sh judge-score later)"; fi
else
  echo "skipped: needs the practice run first"
fi

hdr "6/8  Second open model (qwen) on the same 30 jobs (optional comparison)"
bash "$R" qwen

hdr "7/8  README results block from the results files"
bash "$R" results

hdr "8/8  Commit, push to GitHub, source zip"
bash "$R" push
OUTZIP="${USERPROFILE:-$HOME}/Documents/gigbid_source.zip"
[ -d "$(dirname "$OUTZIP")" ] || OUTZIP="$HOME/gigbid_source.zip"
git archive --format=zip -o "$OUTZIP" HEAD && echo "source zip: $OUTZIP"

hdr "Summary"
bash "$R" summary
missing=()
for f in pipeline_open_dev.json pipeline_open_dev_injection.json pipeline_open_dev_injection_nodefence.json pipeline_open_heldout.json \
         agents_compare.json pipeline_open_real.json judge_calibration.json pipeline_open_qwen_dev.json; do
  ok_file "$f" || missing+=("$f")
done
if grep -rqs "daily quota exhausted" data/runtime/laptop_*.log; then
  echo "Groq's daily quota ran out during this run."
fi
if [ ${#missing[@]} -eq 0 ]; then
  echo "ALL DONE. Everything is pushed; tell Claude so the report PDF can be rebuilt from the new results."
else
  echo "Not finished yet: ${missing[*]}"
  echo "Run RUN_EVERYTHING.bat again after the Groq quota resets (finished calls are cached and cost nothing)."
fi
