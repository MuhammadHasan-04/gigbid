"""Regenerate the README results block from evals/results (so every number traces to a file).

python scripts/update_readme.py [profile]      (default: heuristic; uses open-profile files when present)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "evals" / "results"
P = sys.argv[1] if len(sys.argv) > 1 else "heuristic"


def load(name):
    f = RES / name
    return json.loads(f.read_text()) if f.exists() else None


def o(tag):
    d = load(f"pipeline_{tag}.json")
    return d["overall"]["overall"] if d else None


rag = load(f"rag_{P}.json")["summary"]
rag_ho = load(f"rag_{P}_heldout.json")["summary"]
best, ho = o(f"{P}_dev"), o(f"{P}_heldout")
rows = [("V0 naive dense", "v0", o(f"{P}_dev_rag_v0")), ("V5 multi-vector", "v5", o(f"{P}_dev_rag_v5")),
        ("V8 corrective loop", "v8", o(f"{P}_dev_rag_v8")),
        ("**Shipped (best)**: decompose + hybrid + contextual + structural", "best", best)]
cost = "0 (rules)" if P == "heuristic" else None


def row(name, key, p):
    r = rag[key]
    if not p:
        return f"| {name} | {r['recall5']} | {r['mrr']} | {r['ndcg10']} | – | – | – | – | – |"
    judge = p.get("judge_score") if p.get("judge_score") is not None else "n/a"
    c = cost or p.get("usd_per_proposal")
    return (f"| {name} | {r['recall5']} | {r['mrr']} | {r['ndcg10']} | {p['unsupported_before']} → {p['unsupported_after']} | {judge} | "
            f"{p['gigsim_reply_rate']} | {p['p95_latency_s_job']} | {c} |")


ab = load(f"ab_test_{P}.json")
ts = load("tool_study.json")
ac = load("agents_compare.json")
lines = [
    f"**RAG variants** (dev set, {rag['v0']['n']} jobs with gold evidence, `evals/results/rag_{P}.json`; unsupported claims, reply rate and latency from `pipeline_{P}_dev*.json`)",
    "",
    "| Variant | Evidence Recall@5 | MRR | nDCG@10 | Unsupported claims / proposal (before → after verification) | Judge score | GigSim reply rate | p95 latency per job (s) | Cost per proposal (USD) |",
    "|---|---|---|---|---|---|---|---|---|",
    *[row(*r) for r in rows],
    "",
    f"Held-out (`rag_{P}_heldout.json`): V0 nDCG@10 {rag_ho['v0']['ndcg10']} vs shipped {rag_ho['best']['ndcg10']}.",
    "",
    f"**Decisions and safety** (dev, {best['n_jobs']} jobs, `pipeline_{P}_dev.json`): bid-or-skip F1 {best['bid_f1']}, scam precision "
    f"{best['scam_precision']}, recall {best['scam_recall']}, price inside the fair band {best['price_in_band']}, injection attack success "
    f"{best['injection_attack_success_rate']} on the {best['injection_drafted']} drafted injected jobs ({best['injection_jobs']} injected jobs in total). "
    f"Held-out (`pipeline_{P}_heldout.json`): F1 {ho['bid_f1']}, GigSim reply rate {ho['gigsim_reply_rate']}.",
    "",
]
if ac:
    r = ac["results"]
    lines += ["**Multi-agent comparison** (`agents_compare.json`)", "", "| System | Bid/skip accuracy | Unsupported claims / proposal | Compliance violations | GigSim reply rate | Tokens / job | p95 latency (s) |", "|---|---|---|---|---|---|---|"]
    for k, label in (("react", "Single ReAct agent"), ("supervisor", "langgraph-supervisor"), ("graph", "GigBid graph")):
        if k in r:
            x = r[k]
            lines.append(f"| {label} | {x['bid_skip_accuracy']} | {x['unsupported_claims_per_proposal']} | {x['compliance_violations_in_output']} | {x['gigsim_reply_rate']} | {x['tokens_per_job']} | {x['p95_latency_s']} |")
    lines.append("")
else:
    lines += ["**Multi-agent comparison** (R&D C): single ReAct agent vs `langgraph-supervisor` vs this graph needs a model endpoint. Runner: `evals/runners/agents_compare.py`. Pending.", ""]
if ts:
    m = ts["model"]["model"]
    lines += [f"**Tool granularity** (R&D A, `tool_study.json`, {m} on Groq, {ts['toolsets']['best']['n']} tasks)", "",
              "| Tool set | # tools | Tool-selection accuracy | Argument accuracy | Tokens / task |", "|---|---|---|---|---|"]
    for k, label in (("fine", "Fine-grained"), ("coarse", "Coarse (action enum)"), ("best", "Shipped, rewritten descriptions")):
        x = ts["toolsets"][k]
        lines.append(f"| {label} | {x['n_tools']} | {x['tool_selection_accuracy']} | {x['argument_accuracy']} | {x['tokens_per_task']} |")
    lines.append("")
od, oq, oh = o("open_dev"), o("open_qwen_dev"), o("open_heldout")
oi, oin = o("open_dev_injection"), o("open_dev_injection_nodefence")
jc = load("judge_calibration.json")
if od:
    lines += ["**Model-backed runs (open profile on Groq free tier; small samples, jobs that fell back to rules excluded)**", "",
              "| Run | Model(s) | Jobs | Bid F1 | Scam recall | Price in band | Proposals | Unsupported before → after | Judge | GigSim reply | Tokens/job | USD/proposal |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for tag, label, model in (("open_dev", "Dev", "gpt-oss-20b + 120b"), ("open_qwen_dev", "Dev", "qwen3.8-27b"), ("open_heldout", "Held-out", "gpt-oss-20b + 120b")):
        x = o(tag)
        if x:
            lines.append(f"| {label} (`pipeline_{tag}.json`) | {model} | {x['n_jobs']} | {x['bid_f1']} | {x['scam_recall']} | {x['price_in_band']} | {x['n_proposals']} | "
                         f"{x['unsupported_before']} → {x['unsupported_after']} | {x['judge_score'] if x.get('judge_score') is not None else 'n/a'} | {x['gigsim_reply_rate']} | {x['tokens_per_job']} | {x['usd_per_proposal']} |")
    lines.append("")
if oi and oin:
    lines.append(f"**Prompt injection, model writer** (`pipeline_open_dev_injection*.json`): attack success {oi['injection_attack_success_rate']} with defences "
                 f"vs {oin['injection_attack_success_rate']} without, on {oi['injection_drafted']} / {oin['injection_drafted']} drafted injected jobs.")
    lines.append("")
if jc:
    lines.append(f"**Judge calibration** (`judge_calibration.json`): Cohen's kappa {jc['cohen_kappa']}, quadratic-weighted {jc['quadratic_weighted_kappa']}, "
                 f"exact agreement {jc['exact_agreement']} on {jc['n']} proposals scored by the author.")
    lines.append("")
if ab:
    lines.append(f"**Signature extension X2** (`ab_test_{P}.json`): evidence-first (A) {ab['reply_rate_A']} vs question-first (B) {ab['reply_rate_B']} reply rate on "
                 f"{ab['n_paired']} paired jobs, McNemar exact p = {ab['mcnemar_exact_p']}.")
block = "\n".join(lines)
s = (ROOT / "README.md").read_text()
s = re.sub(r"<!-- results:start -->.*<!-- results:end -->", "<!-- results:start -->\n" + block + "\n<!-- results:end -->", s, flags=re.S)
(ROOT / "README.md").write_text(s)
print(block)
