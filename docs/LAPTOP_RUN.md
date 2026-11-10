# Running the remaining model experiments on your laptop

Windows: use **Git Bash** (comes with Git for Windows) or **WSL**. You need Python 3.12 and Git.

```bash
git clone https://github.com/MuhammadHasan-04/gigbid.git
cd gigbid
echo "GROQ_API_KEY=gsk_your_key_here" > .env     # your Groq key; .env is git-ignored
echo "MODEL_PROFILE=open" >> .env
./scripts/laptop_run.sh setup          # ~5 min: venv, packages, simulator data, checks Groq answers
./scripts/laptop_run.sh dev            # 30 practice jobs + injection test (~1-2 h, free-tier rate limits)
./scripts/laptop_run.sh judge-export   # then fill human_score (1-5) in evals/datasets/judge_labels.csv
./scripts/laptop_run.sh judge-score    # kappa between you and the LLM judge
./scripts/laptop_run.sh heldout        # held-out run + second open model (qwen)
./scripts/laptop_run.sh compare        # single agent vs supervisor vs graph (R&D C)
./scripts/laptop_run.sh results        # README results block regenerated from the files
./scripts/laptop_run.sh push           # commit + push (GitHub sign-in prompt the first time)
./scripts/laptop_run.sh summary        # what is done so far
```

If a step prints `daily quota exhausted` (Groq free tier: 200k tokens per day per model), run the same step
again later. Finished calls are cached, and jobs that fell back to rules are excluded, so nothing is double-counted.
Every step writes a log to `data/runtime/laptop_*.log`.
