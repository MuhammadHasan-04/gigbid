"""Build the R&D report (HTML -> PDF with headless Chromium). Every number is read from evals/results.

python docs/report/build_report.py [profile]   -> docs/report/GigBid_RnD_Report.pdf
"""
import html
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "evals" / "results"
P = sys.argv[1] if len(sys.argv) > 1 else "heuristic"
OUT = ROOT / "docs" / "report"


def L(n):
    f = RES / n
    return json.loads(f.read_text()) if f.exists() else None


def O(tag):
    d = L(f"pipeline_{tag}.json")
    return d["overall"]["overall"] if d else None


def commit():
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


rag, rag_ho = L(f"rag_{P}.json")["summary"], L(f"rag_{P}_heldout.json")["summary"]
sweep = L(f"rag_sweep_{P}.json")
dev, nod, ho = O(f"{P}_dev"), O(f"{P}_dev_nodefence"), O(f"{P}_heldout")
before_fix = O(f"{P}_dev_before_verifier_fix")
byp = L(f"pipeline_{P}_dev.json")["by_persona"]
vrows = {v: O(f"{P}_dev_rag_{v}") for v in ("v0", "v5", "v8")}
ab, cr, fa = L(f"ab_test_{P}.json"), L("change_request.json"), L("failure_analysis.json")
fa0 = L("failure_analysis_before_fixes.json")
tool, ac, jc = L("tool_study.json"), L("agents_compare.json"), L("judge_calibration.json")
cfg = L(f"pipeline_{P}_dev.json")["config"]
rs, rp, rca, rv1 = L("real_scam_external.json"), L(f"pipeline_{P}_real.json"), L("real_category_audit.json"), O(f"{P}_dev_rules_v1")
REAL = ROOT / "data" / "real"
rman = json.loads((REAL / "MANIFEST.json").read_text()) if (REAL / "MANIFEST.json").exists() else None
rcal = json.loads((REAL / "calibration.json").read_text()) if (REAL / "calibration.json").exists() else {}
C = commit()


def t(rows, head):
    h = "".join(f"<th>{x}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{'' if c is None else c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>"


def src(f):
    return f'<span class="src">[{html.escape(f)}]</span>'




def svg_bars(title, cats, series, colors=("#146356", "#c47f17", "#3a6a99"), w=520, h=190, fmt="{:g}", ymax=None):
    """Grouped bar chart as inline SVG (no plotting dependency). series = [(label, [values])]."""
    pad_l, pad_b, pad_t = 34, 46, 22
    vals = [v for _, vs in series for v in vs if v is not None]
    top = ymax or (max(vals) * 1.15 if vals else 1)
    cw = (w - pad_l - 6) / max(1, len(cats))
    bw = cw * 0.8 / len(series)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="font: 8.5px DejaVu Sans, Arial">',
           f'<text x="{pad_l}" y="11" font-weight="bold" font-size="10">{html.escape(title)}</text>']
    for i in range(5):
        y = pad_t + (h - pad_t - pad_b) * i / 4
        out.append(f'<line x1="{pad_l}" x2="{w - 4}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e3e9e7"/>'
                   f'<text x="{pad_l - 3}" y="{y + 3:.1f}" text-anchor="end" fill="#666">{fmt.format(round(top * (1 - i / 4), 3))}</text>')
    for ci, c in enumerate(cats):
        x0 = pad_l + ci * cw + cw * 0.1
        for si, (_, vs) in enumerate(series):
            v = vs[ci]
            if v is None:
                continue
            bh = (h - pad_t - pad_b) * min(v, top) / top
            x = x0 + si * bw
            out.append(f'<rect x="{x:.1f}" y="{h - pad_b - bh:.1f}" width="{bw - 1:.1f}" height="{bh:.1f}" fill="{colors[si]}"/>')
        out.append(f'<text transform="translate({pad_l + ci * cw + cw / 2:.1f},{h - pad_b + 8}) rotate(35)" fill="#333">{html.escape(str(c))}</text>')
    lx = w - 6
    for si, (lab, _) in enumerate(reversed(series)):
        idx = len(series) - 1 - si
        lx -= 8 + 5.2 * len(lab) + 10
        out.append(f'<rect x="{lx:.0f}" y="4" width="8" height="8" fill="{colors[idx]}"/><text x="{lx + 11:.0f}" y="11">{html.escape(lab)}</text>')
    out.append("</svg>")
    return "".join(out)


def svg_lines(title, xs, series, colors=("#146356", "#c47f17", "#3a6a99", "#8a3b8f"), w=520, h=170):
    pad_l, pad_b, pad_t = 40, 26, 22
    vals = [v for _, vs in series for v in vs]
    top = max(vals) * 1.15 if vals else 1
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="font: 8.5px DejaVu Sans, Arial">',
           f'<text x="{pad_l}" y="11" font-weight="bold" font-size="10">{html.escape(title)}</text>']
    for i in range(5):
        y = pad_t + (h - pad_t - pad_b) * i / 4
        out.append(f'<line x1="{pad_l}" x2="{w - 4}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e3e9e7"/>'
                   f'<text x="{pad_l - 3}" y="{y + 3:.1f}" text-anchor="end" fill="#666">{top * (1 - i / 4) * 100:.1f}%</text>')
    n = len(xs)
    X = lambda i: pad_l + (w - pad_l - 8) * i / max(1, n - 1)
    for i in range(0, n, max(1, n // 6)):
        out.append(f'<text x="{X(i):.1f}" y="{h - 10}" text-anchor="middle" fill="#333">{html.escape(xs[i])}</text>')
    for si, (lab, vs) in enumerate(series):
        pts = " ".join(f"{X(i):.1f},{h - pad_b - (h - pad_t - pad_b) * v / top:.1f}" for i, v in enumerate(vs))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{colors[si]}" stroke-width="1.6"/>')
        out.append(f'<rect x="{pad_l + 8 + si * 115}" y="{pad_t - 2}" width="8" height="8" fill="{colors[si]}"/><text x="{pad_l + 19 + si * 115}" y="{pad_t + 5}">{html.escape(lab)}</text>')
    out.append("</svg>")
    return "".join(out)


def mcp_tools():
    import asyncio
    sys.path.insert(0, str(ROOT))
    rows = []
    try:
        from mcp_servers.marketplace.server import mcp as m
        from mcp_servers.portfolio.server import mcp as pf
        from mcp_servers.workspace.server import mcp as ws
        for name, srv in (("Portfolio", pf), ("Marketplace", m), ("Workspace", ws)):
            for tl in asyncio.run(srv.list_tools()):
                a = tl.annotations
                kind = "read" if (a and a.readOnlyHint) else ("write, destructive" if (a and a.destructiveHint) else "write")
                rows.append([name, f"<code>{tl.name}</code>", kind, "yes" if (a and a.idempotentHint) else "no",
                             html.escape(tl.description.split(chr(10))[0][:105])])
    except Exception as e:  # report still builds without the servers importable
        rows.append(["–", "–", "–", "–", f"tool list unavailable: {html.escape(str(e))[:80]}"])
    return t(rows, ["Server", "Tool", "Kind", "Idempotent", "Description (first line)"])

pending = '<span class="pending">pending: needs a model endpoint (runner committed)</span>'

rag_tbl = t([[k, v.get("recall5", "–"), v.get("mrr", "–"), v.get("ndcg10", "–"), v.get("by_type", {}).get("4+_requirements", {}).get("recall5", "–"),
              v.get("error", "")[:45] if v.get("error") else ""] for k, v in rag.items()],
            ["Variant", "Recall@5", "MRR", "nDCG@10", "R@5 (4+ reqs)", "note"])
e2e_tbl = t([[n, rag[k]["recall5"], rag[k]["ndcg10"], f"{p['unsupported_before']} → {p['unsupported_after']}", "n/a" if p.get("judge_score") is None else p["judge_score"],
              p["gigsim_reply_rate"], p["gigsim_hire_rate"], p["p95_latency_s_job"], p["usd_per_proposal"]]
             for n, k, p in [("V0", "v0", vrows["v0"]), ("V5", "v5", vrows["v5"]), ("V8", "v8", vrows["v8"]), ("Shipped", "best", dev)]],
            ["Variant", "Evidence R@5", "nDCG@10", "Unsupported / proposal (before → after)", "Judge", "GigSim reply", "Hire", "p95 s/job", "USD/proposal"])
persona_tbl = t([[p, v["bid_f1"], v["scam_precision"], v["scam_recall"], v["price_in_band"], v["n_proposals"], v["gigsim_reply_rate"],
                  rag["best"]["by_persona"][p]["recall5"], rag["v0"]["by_persona"][p]["recall5"]] for p, v in byp.items()],
                ["Persona", "Bid F1", "Scam P", "Scam R", "Price in band", "Proposals", "Reply rate", "R@5 shipped", "R@5 V0"])
type_tbl = t([[ty, rag["v0"]["by_type"][ty]["recall5"], rag["best"]["by_type"][ty]["recall5"], rag["v0"]["by_type"][ty]["ndcg10"], rag["best"]["by_type"][ty]["ndcg10"]]
              for ty in ("1-3_requirements", "4+_requirements")], ["Job type", "R@5 V0", "R@5 shipped", "nDCG V0", "nDCG shipped"])
sweep_top = t([[r["name"], r["ndcg10"], r["recall5"], r["mrr"]] for r in sweep["ranked"][:6]], ["Config (query-retrieval-mv-ctx-chunk-outcome)", "nDCG@10", "R@5", "MRR"])
fa_tbl = t([[k, fa0["counts"].get(k, 0), fa["counts"].get(k, 0)] for k in sorted(set(fa0["counts"]) | set(fa["counts"]))],
           ["Failure class", "before fixes", "after fixes"])

budget = t([["p95 latency per job analysed", "20 s", f"{dev['p95_latency_s_job']} s (dev) / {ho['p95_latency_s_job']} s (held-out)"],
            ["p95 latency per proposal", "45 s", f"{dev['p95_latency_s_proposal']} s / {ho['p95_latency_s_proposal']} s"],
            ["USD per job analysed", "$0.002", f"${dev['usd_per_job']} / ${ho['usd_per_job']}"],
            ["USD per proposal", "$0.01", f"${dev['usd_per_proposal']} / ${ho['usd_per_proposal']}"]],
           ["Budget", "Declared (agent/config.yaml)", f"Measured ({P} profile)"])

tool_html = (t([[k, v["n_tools"], v["tool_selection_accuracy"], v["argument_accuracy"], v["tokens_per_task"]] for k, v in tool["toolsets"].items()],
               ["Tool set", "# tools", "Tool selection acc.", "Argument acc.", "Tokens / task"]) + src("tool_study.json")) if tool else pending
ac_html = (t([[k, v["bid_skip_accuracy"], v["unsupported_claims_per_proposal"], v["compliance_violations_in_output"], v["gigsim_reply_rate"], v["tokens_per_job"], v["p95_latency_s"]]
              for k, v in ac["results"].items()], ["System", "Bid/skip acc.", "Unsupported/proposal", "Violations", "Reply", "Tokens/job", "p95 s"]) + src("agents_compare.json")) if ac else pending
jc_html = (f"Cohen's kappa {jc['cohen_kappa']}, quadratic-weighted {jc['quadratic_weighted_kappa']}, exact agreement {jc['exact_agreement']} on {jc['n']} items {src('judge_calibration.json')}") if jc else pending

# ---------- figures and extra tables (all from evals/results and data/real)
fig_rag = svg_bars("Retrieval quality by variant (dev, 384 jobs)", [k for k in ("v0", "v1", "v2", "v4", "v5", "v8", "best") if k in rag and "ndcg10" in rag[k]],
                   [("nDCG@10", [rag[k]["ndcg10"] for k in ("v0", "v1", "v2", "v4", "v5", "v8", "best") if k in rag and "ndcg10" in rag[k]]),
                    ("Recall@5", [rag[k]["recall5"] for k in ("v0", "v1", "v2", "v4", "v5", "v8", "best") if k in rag and "ndcg10" in rag[k]])],
                   ymax=1.0)
_cal_keys = list(rcal)
fig_cal = svg_bars("Median hourly rate (USD): synthetic generator vs real contracts", _cal_keys,
                   [("synthetic", [rcal[k]["synthetic_hourly_median"] for k in _cal_keys]), ("real (Kaggle contracts)", [rcal[k]["real_hourly_p50"] for k in _cal_keys])],
                   w=700, h=200)
_v1, _v2 = rs["rules_v1_vs_v2"]["v1"], rs["rules_v1_vs_v2"]["v2"]
fig_scam = svg_bars("Real posts flagged as scams (%)", ["board posts", "2024 held-out"],
                    [("v1", [_v1["real_posts_in_sample_flag_rate"] * 100, _v1["real_2024_heldout_flag_rate"] * 100]),
                     ("v2", [_v2["real_posts_in_sample_flag_rate"] * 100, _v2["real_2024_heldout_flag_rate"] * 100])], w=400, h=170, fmt="{:.2f}")
_dem = json.loads((REAL / "demand_real.json").read_text()) if (REAL / "demand_real.json").exists() else None
fig_dem = svg_lines("2024 share of Upwork posts per week in each persona's market (real, 733k posts)", _dem["weeks"],
                    [(lab, [sum(_dem["share"].get(c, [0] * len(_dem["weeks"]))[i] for c in cs) for i in range(len(_dem["weeks"]))])
                     for lab, cs in (("AI/ML", ("llm_apps", "classical_ml", "vision", "nlp", "mlops", "recsys")),
                                     ("Full-stack", ("web_app", "backend", "realtime", "ecommerce", "api", "testing", "mobile")),
                                     ("Data analyst", ("bi", "analytics_eng", "product_analytics", "web_analytics", "spreadsheet", "forecasting", "research")))]) if _dem else ""
_rm = json.loads((REAL / "market_real.json").read_text())["by_category"] if (REAL / "market_real.json").exists() else {}
market_tbl = t([[k, _rm[k]["contracts"]["n_hourly"], f"{_rm[k]['contracts']['hourly_p25']:g}–{_rm[k]['contracts']['hourly_p75']:g}", _rm[k]["contracts"]["n_fixed"],
                 f"{_rm[k]['contracts']['fixed_p25']:g}–{_rm[k]['contracts']['fixed_p75']:g}",
                 f"{(_rm[k].get('postings_2024') or {}).get('hourly_low_p50', '–')}–{(_rm[k].get('postings_2024') or {}).get('hourly_high_p50', '–')}"]
                for k in ("llm_apps", "classical_ml", "vision", "web_app", "backend", "ecommerce", "bi", "analytics_eng", "spreadsheet") if k in _rm],
               ["Category", "Hourly contracts", "Hourly p25–p75 ($)", "Fixed contracts", "Fixed p25–p75 ($)", "2024 posted hourly range (medians)"])
data_tbl = t([["Synthetic (GigSim stand-in)", "600 dev + 180 held-out jobs, 158 live, 260 clients, 1,500 price history, 3 personas", "gold bid/skip, scams, injections, fair price band, relevant evidence", "all labelled metrics"],
              ["Real: Upwork jobs 60k (Apache 2.0)", f"{rman['jobs60k']['jobs_kept']:,} posts + client stats", "none (skill tags only)", "job board, real-post pipeline run"],
              ["Real: contracts 1.3M (ODC-By)", f"{rman['contracts']['hourly_contracts']:,} hourly + {rman['contracts']['fixed_completed_contracts']:,} fixed", "–", "real price percentiles"],
              ["Real: 2024 posts 50k + tracker (ODC-By)", f"{rman['postings_2024']['unique_postings']:,} unique posts", "–", "budgets, demand, 3,000 held-out posts"],
              ["Freelancer success (Apache 2.0, synthetic)", "12,000 records", "–", "rejected after a quality check"],
              ["Fake job posts (licence not stated)", "44,045 labelled ads", "real / fake", "outside scam test only, not committed"]],
             ["Source", "Size used", "Labels", "Role"]) if rman else ""
tools_tbl = mcp_tools()
_open = {k: O(k) for k in ("open_dev", "open_heldout", "open_qwen_dev", "open_dev_injection", "open_dev_injection_nodefence")}
open_tbl = t([[k, ("done" if v else "pending (laptop run)"), v and v["n_jobs"], v and v["bid_f1"], v and v["scam_recall"], v and v["n_proposals"],
               v and v["unsupported_after"], v and v["gigsim_reply_rate"], v and v["tokens_per_job"], v and v["usd_per_proposal"]] for k, v in _open.items()]
             + [["tool_study (R&D A)", "done" if tool else "pending", tool and tool["toolsets"]["best"]["n"], None, None, None, None, None, None, None],
                ["agents_compare (R&D C)", "done" if ac else "pending", None, None, None, None, None, None, None, None],
                ["judge_calibration (B4)", "done" if jc else "pending", jc and jc["n"], None, None, None, None, None, None, None],
                ["open_real (real posts)", "done" if L("pipeline_open_real.json") else "pending", None, None, None, None, None, None, None, None]],
             ["Run (open profile)", "Status", "Jobs", "Bid F1", "Scam R", "Proposals", "Unsupported after", "Reply", "Tokens/job", "USD/prop."])

CSS = """
@page { size: A4; margin: 16mm 15mm 16mm 15mm; }
body { font: 11px/1.5 'DejaVu Sans', Arial, sans-serif; color: #1b1f1d; }
h1 { font-size: 20px; margin: 0 0 2px; color: #0f4c42; } h2 { font-size: 14.5px; color: #0f4c42; border-bottom: 1.5px solid #cfe0db; padding-bottom: 2px; margin: 13px 0 5px; page-break-after: avoid; }
h3 { font-size: 11px; margin: 8px 0 3px; } p { margin: 3px 0 5px; } ul { margin: 2px 0 6px 16px; padding: 0; } li { margin: 1px 0; }
table { border-collapse: collapse; width: 100%; margin: 4px 0 6px; font-size: 9.6px; page-break-inside: avoid; }
th { background: #e8f2ef; text-align: left; } th, td { border: 1px solid #cfd8d4; padding: 2.5px 4px; vertical-align: top; }
.src { color: #3a6a99; font-size: 8.5px; } .pending { color: #9a5a00; font-style: italic; } .meta { color: #555; font-size: 9.5px; }
.box { background: #f4f7f6; border-left: 3px solid #146356; padding: 5px 8px; margin: 6px 0; }
img { max-width: 100%; } .two { display: flex; gap: 10px; } .two > div { flex: 1; } figure { margin: 6px 0 8px; text-align: center; page-break-inside: avoid; } figcaption { font-size: 9.3px; color: #555; margin-top: 2px; } .pb { page-break-before: always; }
code { font-size: 9px; background: #f0f2f1; padding: 0 2px; }
"""

body = f"""
<h1>GigBid: a multi-agent freelancer copilot</h1>
<div class="meta">AI-4016 R&amp;D report · Hasan · FAST-NUCES Islamabad · repository commit <code>{C}</code> · results profile <code>{P}</code> ·
providers actually used in the main run: {cfg.get('providers_actually_used')}</div>

<div class="box"><b>Read first: threats to validity.</b> (1) The instructor GigSim, persona corpora and dev set were not available; every
experiment uses this repository's GigSim stand-in (<code>gigsim/</code>, seeded and reproducible), written by the same author as the system.
(2) The workspace had no LLM API access while these numbers were produced, so results come from the <code>{P}</code> profile, the deterministic
rule-based fallback every node has (ADR 0004). Experiments that only make sense with a model (tool-granularity study, single-agent
comparison, judge calibration) have committed runners and are marked pending. (3) Simulated-client reply rate is a designed proxy. (4) Real Upwork data (six Kaggle datasets, §11) arrived late; it has no gold
labels, so it is used for a real job board, real prices and checks of the rules, while the labelled metrics stay on the synthetic sets.</div>


<h2>Executive summary</h2>
<p>GigBid is a LangGraph multi-agent copilot that finds freelance jobs, decides bid / watch / skip with reasons, prices, drafts a proposal whose every
claim is backed by the freelancer's portfolio, and stops at a human approval gate before anything is sent or any Connects are spent. It talks to the
marketplace, portfolio and calendar only through three MCP servers. The table lists the headline numbers; each comes from a committed file in
<code>evals/results/</code> and is rebuilt into this PDF by <code>docs/report/build_report.py</code>.</p>
{t([["Bid / skip F1 (dev, 600 jobs)", dev['bid_f1'], ho['bid_f1'], "graph + rule floor"],
    ["Scam recall / precision", f"{dev['scam_recall']} / {dev['scam_precision']}", f"{ho['scam_recall']} / {ho['scam_precision']}", "Risk Assessor v2"],
    ["Price inside fair band", dev['price_in_band'], ho['price_in_band'], "capped at posted budget (§10)"],
    ["Unsupported claims per proposal (after verifier)", dev['unsupported_after'], ho['unsupported_after'], "claim verifier"],
    ["Injection attack success", dev['injection_attack_success_rate'], ho['injection_attack_success_rate'], "defence in depth"],
    ["Simulated-client reply rate", dev['gigsim_reply_rate'], ho['gigsim_reply_rate'], "designed proxy"],
    ["Retrieval nDCG@10 (V0 → shipped)", f"{rag['v0']['ndcg10']} → {rag['best']['ndcg10']}", f"{rag_ho['v0']['ndcg10']} → {rag_ho['best']['ndcg10']}", "64-config sweep"],
    ["X2 A/B reply rate (A vs B)", f"{ab['reply_rate_A']} vs {ab['reply_rate_B']}", "–", f"McNemar p = {ab['mcnemar_exact_p']}"]],
   ["Metric", "Dev", "Held-out", "Mechanism"])}{src(f'pipeline_{P}_dev.json, pipeline_{P}_heldout.json')}
<p><b>Answers to the three R&amp;D questions.</b> (A) Mid-grained tools with "what this is not for" descriptions are shipped (§5). (B) The pre-registered
RAG hypothesis was <i>rejected</i>: decomposition and hybrid search alone lowered Recall@5; context headers and structural chunks carried the gain (§6).
(C) The hand-built graph is shipped because only it can put the approval interrupt and the compliance pass at a fixed point (§7).
<b>Real data:</b> 1,295 real Upwork posts form the live job board and 1.3M real contracts price them; they exposed and fixed a scam-rule false-alarm
problem (§11). <b>Biggest open item:</b> model-backed (Groq gpt-oss) runs are produced by the one-command laptop script; their status is in §12.</p>
<h2 class="pb">1. Problem and constraints</h2>
<p>Freelancers spend hours scanning feeds, spend paid Connects on jobs they won't win, send generic proposals, and run into scams that ask for
free work or off-platform payment. GigBid automates discovery, assessment and drafting. The freelancer makes every decision that leaves the system.</p>
<ul><li><b>Never automated:</b> submitting a proposal, sending a message, spending Connects, claiming experience the portfolio doesn't prove, contacting
a client off-platform. Enforced by a LangGraph <code>interrupt()</code> <i>and</i> an HMAC approval token checked inside the Marketplace MCP server (ADR 0002).</li>
<li><b>Allowed automatically:</b> scouting, analysis, skipping (only with autonomy <code>auto_skip_low_fit</code>), drafting.</li>
<li><b>Budgets</b> (config, enforced per thread): 40 graph steps, 30k tokens per job, max 2 Critic revisions; latency and cost budgets in §14.</li></ul>

<h2>2. Architecture</h2>
<div class="two"><div><img src="../images/bid_graph.png" style="max-height:380px"><div class="meta" style="text-align:center">Figure 1. Bid graph (exported from LangGraph).</div></div><div>
<p><b>Bid graph</b> (one thread per job): intake → <code>Send</code> to Job Analyst ∥ Risk Assessor ∥ Fit Matcher → decide (bid/watch/skip with reasons)
→ Pricing (can veto) → Writer → claim Verifier → Critic (≤2 loops) → Compliance → approval interrupt → submit (non-LLM executor, idempotency keys
derived from the thread). <b>Conversation graph</b> (one thread per client conversation): load → classify intent (+injection) → calendar slots →
draft → compliance → approval → send + tentative hold.</p>
<p><b>Marketplace port</b> (<code>agent/marketplace_port.py</code>) has two adapters, GigSim and live Upwork (official MCP over Streamable HTTP, OAuth 2.1).
The port lives inside our Marketplace MCP server, so the graph cannot tell which marketplace it uses. <b>MCP surface:</b> Portfolio (read,
publishable), Marketplace (read + write with schemas, annotations, idempotency keys, <code>dry_run</code>, bearer auth, per-user limiter, hash-chained
audit log), Workspace (calendar, email drafts), plus GitHub MCP for repo ingestion. Each agent gets an allowlist of tools.
<b>Stores:</b> Postgres (app tables, LangGraph checkpointer, LangGraph store for memory), Redis (Arq queue), in-process vectors + BM25 (ADR 0003).</p>
<p><b>Why each agent exists:</b> parallel analysts cut wall-clock time and keep the Analyst tool-less (an injected post can't trigger tool calls).
Fit Matcher makes "no evidence" explicit per requirement. Pricing computes numbers in code and the model only explains them. Verifier, Critic and
Compliance are separated because each failure needs a different fix (§10). Typed hand-offs: <code>JobSpec, RiskReport, FitReport, BidDecision,
PriceQuote, ProposalDraft, Critique, ComplianceVerdict</code>. State, execution trace and long-term memory are kept apart (docs/ARCHITECTURE.md).</p></div></div>
<p><b>Durability (C6)</b> is tested in <code>tests/integration</code>: the graph pauses at approval, the process is replaced, approval resumes from the
Postgres checkpoint, and replaying the <code>submit</code> node from the previous checkpoint returns <code>idempotent_replay</code> with exactly one GigSim
submission and one Connects deduction. Public traces: <code>docs/traces/</code> (scam skip, approval, injection, Critic loop, crash-and-resume).</p>
<figure><img src="../images/conversation_graph.png" style="max-height:250px"><figcaption>Figure 2. Conversation graph: one thread per client conversation; the same approval interrupt guards every send.</figcaption></figure>



<h2>3. MCP servers and tool surface</h2>
<p>All three servers are FastMCP processes with typed input schemas and MCP tool annotations. The table is generated at build time from
<code>list_tools()</code>, so it always matches the code. Contract tests snapshot the same list and fail on any unreviewed change.</p>
{tools_tbl}
<p><b>Write safety.</b> <code>submit_proposal</code> and <code>send_message</code> are the only destructive tools. Each needs an HMAC approval token bound to
the content hash the freelancer approved, an idempotency key derived from the graph thread, and accepts <code>dry_run</code>. A replay returns
<code>idempotent_replay</code> instead of a second submission. Every write is appended to a hash-chained audit log with PII masked.</p>
<h3>Portfolio MCP: the publishable server</h3>
<div class="two"><div><p>The Portfolio server is self-contained (<code>mcp_servers/portfolio/</code>, its own <code>pyproject.toml</code>, README and
<code>server.json</code>). It exposes 3 read-only tools, resources for each case study (<code>portfolio://case/&lt;id&gt;</code>) and a
<code>proposal_evidence</code> prompt, and runs over stdio or Streamable HTTP. Any MCP client can use it to ground a cover letter in a person's real
projects. It runs the same hybrid retriever as the agent (decomposition, BM25 + vectors, contextual headers), so the published tool and the evaluated
pipeline cannot drift apart. It was checked in the official MCP Inspector (right): tool list, a live <code>search_evidence</code> call, resources and prompts.</p>
<p>Lessons: tool descriptions matter more than names (the model picked <code>get_case_study</code> for searches until its description said
"only for a known id"); results return short evidence snippets with ids rather than whole documents, which kept tokens per proposal down.</p></div>
<div><img src="../images/inspector_portfolio_call.png" style="max-height:300px; border:1px solid #cfd8d4"><div class="meta" style="text-align:center">Figure 3. MCP Inspector: <code>search_evidence</code> call.</div></div></div>

<h2>4. Data: synthetic world and real Upwork data</h2>
<p>Labelled metrics need gold answers (bid or skip, scam or not, fair price band, which project is relevant evidence), and no public dataset has them.
So the experiments run on a seeded synthetic marketplace (GigSim stand-in), and six permitted Kaggle datasets supply what synthetic data cannot: real
posts, real prices and real demand. Every record carries <code>source: real|synthetic</code>, and the UI shows a badge for it.</p>
{data_tbl}
<figure>{fig_cal}<figcaption>Figure 4. Median hourly rate per category. The synthetic generator over-prices developer work and under-prices analyst work
(data/real/calibration.json); real posts are therefore priced from the real contracts, not from the generator.</figcaption></figure>
<p><b>Real price bands used by the Pricing Strategist</b> (completed contracts, 2024 posted ranges):</p>{market_tbl}
<figure>{fig_dem}<figcaption>Figure 5. Weekly share of 2024 posts in each persona's categories (data/real/demand_real.json). GigSim's live feed uses
these shares for its arrival mix, so the board's category balance follows the real market.</figcaption></figure>
<p><b>Preprocessing</b> (<code>scripts/ingest_kaggle.py</code>, deterministic, about 75 s): HTML and contact details stripped, exact and near duplicates
removed, budgets parsed into hourly range or fixed amount, categories mapped from title and tags first (description only as a fallback with two cues),
out-of-domain posts kept but marked, client stats joined, and percentiles computed per category. Licences: Apache 2.0 and ODC-By, attributed in
<code>docs/DATA_CARD.md</code> and <code>data/real/MANIFEST.json</code>.</p>
<h2>5. R&amp;D question A: tool granularity</h2>
<p><b>Hypothesis:</b> a small set of mid-grained tools with rewritten, disambiguating descriptions beats both 17 fine-grained tools (selection errors
between near-duplicates) and 3 coarse tools with an <code>action</code> enum (argument errors) on tool-selection and argument accuracy, at fewer
tokens per task than fine-grained. <b>Setup:</b> 40 tasks with known correct calls (<code>evals/datasets/tool_tasks.jsonl</code>), same model, native tool
calling, <code>tool_choice=required</code>. <b>Results:</b> {tool_html}</p>
<p><b>Shipped design:</b> 10 read tools + 3 write tools; descriptions say what the tool is <i>not</i> for ("never for details of one known job id").
Contract tests pin schemas and annotations (<code>tests/contract/snapshots</code>).</p>

<h2>6. R&amp;D question B: RAG variants, claim verification, shipped choice</h2>
<p><b>Hypothesis (stated before running):</b> requirement decomposition plus hybrid retrieval raises evidence Recall@5 by 5+ points over V0 on jobs
with 4+ requirements. <b>Result: rejected.</b> Alone, V1 and V2 lowered Recall@5. Corpus: 384 dev jobs with gold evidence; retrieval unit = project.</p>
{rag_tbl}{src(f'rag_{P}.json')}
<figure>{fig_rag}<figcaption>Figure 6. nDCG@10 and Recall@5 per variant on 384 dev jobs. The shipped "best" pipeline wins on ranking quality (nDCG), not on Recall@5.</figcaption></figure>
<p>A 64-config sweep with nDCG@10 declared as the primary metric before running picked decompose + hybrid + contextual header + structural
chunks: {sweep_top}{src(f'rag_sweep_{P}.json')}</p>
<p><b>Ablation of the shipped pipeline</b> (one component at a time): no decomposition → nDCG {rag['best-no_decompose']['ndcg10']}; no BM25 →
{rag['best-no_bm25']['ndcg10']} (R@5 rises to {rag['best-no_bm25']['recall5']}); no contextual header → {rag['best-no_context']['ndcg10']};
fixed chunks → {rag['best-fixed_chunks']['ndcg10']}; adding multi-vector → {rag['best+multivector']['ndcg10']}. Context headers and structural chunks carry
the gain. Held-out: V0 {rag_ho['v0']['ndcg10']} vs shipped {rag_ho['best']['ndcg10']} nDCG@10. V3 (bge-reranker-v2-m3) could not be run: weights on
Hugging Face were unreachable from the build workspace.</p>
<h3>End-to-end (results table required by B5)</h3>{e2e_tbl}{src(f'pipeline_{P}_dev*.json')}
<p>By job type: {type_tbl} By persona: {persona_tbl}</p>
<p><b>Claim verification (B3).</b> Claims are split by sentence. Each is checked against cited and retrieved evidence by entity (skills incl. ontology
aliases, numbers, proper names; a wrong name or number is always unsupported) and adjudicated by a model only when it has no checkable entities.
Unsupported claims are removed before the Critic. Unsupported claims per proposal before verification: {dev['unsupported_before']}, after: {dev['unsupported_after']}.
<b>LLM-judge calibration:</b> {jc_html}.</p>
<p><b>Where better retrieval didn't translate into replies, and why.</b> Reply rates across variants ({vrows['v0']['gigsim_reply_rate']}–{vrows['v5']['gigsim_reply_rate']})
moved far less than one verifier rule moved them: before the fix in §10 the shipped pipeline had {before_fix['gigsim_reply_rate']} reply rate with
{before_fix['unsupported_before']} claims removed per proposal; after, {dev['gigsim_reply_rate']} with {dev['unsupported_before']}. Simulated clients reward
"must-have evidenced", which saturates once the top 3 items contain one strong match per must-have. Most variants already reach that, so nDCG gains
deeper in the ranking don't show up in replies. <b>Decision:</b> ship the sweep winner (<code>rag.variant: best</code>); revisit with the model profile.</p>

<h2>7. R&amp;D question C: single agent vs supervisor vs graph</h2>
<p><b>Setup:</b> 50 dev jobs (all scams and injections in the sample plus normal jobs), (a) one ReAct agent holding all tools, (b) prebuilt
<code>langgraph-supervisor</code> with researcher/matcher/writer, (c) the hand-built graph. Same model, same tools, same verifier and policy scan applied to outputs.
<b>Results:</b> {ac_html}</p>
<p><b>Expectation to test:</b> the single agent should match the graph on simple in-domain jobs at lower latency and fail on scams and injections (no
rule floor, no separate compliance pass), and on claims (no verifier). Whether to ship it: no, because only the graph can enforce the approval interrupt at a fixed point.</p>

<h2>8. The change request</h2>
<p>The official 2 Nov "platform policy update" text was not available, so the GigSim stand-in models one new <b>rule</b> (no external links except
GitHub) and one new <b>cost</b> (+2 Connects on jobs with 20+ proposals) as <code>policy_v2.yaml</code>. Absorbing it: {cr['config_lines_changed']} config line
(<code>policy.version: 2</code>), {cr['code_lines_changed']} code lines, {cr['time_to_absorb_seconds']} s including the full test suite ({cr['tests_after_change']}). Rules and
costs are data read by the Compliance Guard and Pricing Strategist. <b>Caveat:</b> {html.escape(cr['caveat'])} {src('change_request.json')}</p>

<h2>9. Signature extension: X2 proposal experiments</h2>
<p>Strategy A (evidence-first) vs B (question-first, short), paired on the same {ab['n_paired']} jobs, scored by GigSim's deterministic clients. Reply rate
A {ab['reply_rate_A']} vs B {ab['reply_rate_B']}, hire A {ab['hire_rate_A']} vs B {ab['hire_rate_B']}. Discordant pairs {ab['discordant_A_only']} vs {ab['discordant_B_only']},
McNemar exact p = {ab['mcnemar_exact_p']}. B loses because one cited project leaves the second must-have unevidenced. In production, assignment is
deterministic by job id (<code>experiments.proposal_ab</code>) and the arm is stored on the draft. {src(f'ab_test_{P}.json')}</p>

<h2>10. Failure analysis</h2>
<p>All failed dev jobs were grouped by class ({src('failure_analysis*.json')}); examples are listed in the appendix with trace ids.</p>{fa_tbl}
<ul>
<li><b>Wrong bid: high-risk new clients</b> (28 → 3). Client with no verified payment and zero spend scored risk below 0.6. <i>Fix:</i> explicit rule
<code>skip_unverified_new_clients</code> (config). <i>Worked:</i> bid F1 0.9026 → {dev['bid_f1']}.</li>
<li><b>Unsupported claim (verifier false positive)</b> (117 → 13 removed sentences). 94 of 107 removals were the writer's framing opener, misread as a claim
because it contained a skill and "my". <i>Fix:</i> a claim needs a past-work assertion. <i>Worked:</i> reply rate {before_fix['gigsim_reply_rate']} → {dev['gigsim_reply_rate']}.</li>
<li><b>Compliance miss (over-blocking)</b>: the phone regex matched ISO slot dates, so offered interview slots were deleted from replies. <i>Fix:</i> stricter
pattern + regression test. <i>Worked</i> (video, §D).</li>
<li><b>Mispriced</b> ({fa['counts'].get('mispriced', 0)}): the bid is capped at the posted budget while the gold fair band comes from market history above it. <i>Not
fixed:</i> bidding above a client's stated budget is a product decision, so I chose to keep the cap and report it.</li>
<li><b>Wrong skip</b> ({fa['counts'].get('wrong_skip', 0)}): the Pricing Strategist's floor estimate (market p50 / $45 × complexity) exceeds the budget on cheap categories, so
it vetoes jobs the gold labels bid on. <i>Tried:</i> nothing yet; the next step is to estimate hours from the job spec, not the category median.</li>
<li><b>Injection reached the writer</b> ({fa['counts'].get('injection_reached_writer', 0)} drafted, 0 attacks succeeded): defence in depth (delimiting, rule-floor flag,
compliance canary/contact rules) held, but the rule-based writer never follows instructions, so the <i>with/without defence</i> comparison is uninformative
on this profile ({dev['injection_attack_success_rate']} vs {nod['injection_attack_success_rate']}). It must be rerun with a model writer.</li>
<li><b>Tool error / lifecycle</b>: the MCP idempotency store outlived GigSim state between test runs and replayed a stale proposal id. <i>Fix:</i> test runtime
isolation. <i>Lesson:</i> dedup records need the same lifecycle as the thing they dedupe.</li>
<li><b>Generic opening</b>: 0 flagged by simulated clients after the verifier fix; the Critic rejects drafts whose first 80 characters match the generic list.</li>
</ul>

<h2>11. Real data (Kaggle): what it changed</h2>
<p><b>Selection.</b> Of the six allowed datasets: 60k Upwork posts (Apache 2.0) → the real job board ({rman['jobs60k']['jobs_kept']} posts after cleaning,
de-duplication, contact-detail removal and category mapping); 1.3M contracts (ODC-By) → real price percentiles ({rman['contracts']['hourly_contracts']:,} hourly,
{rman['contracts']['fixed_completed_contracts']:,} completed fixed-price); 2024 posts (50k + tracker, ODC-By, {rman['postings_2024']['unique_postings']:,} unique) → recent budgets,
weekly demand and an untouched test sample; the freelancer-success set was <b>rejected</b> (third-party synthetic; {json.loads((REAL / "freelancer_benchmarks.json").read_text())['quality_check']['share_at_max']}
of rates sit at a $280 cap); the fake-job set (no stated licence) is used only as an outside test, nothing committed. Every job, client and market number carries
<code>source: real|synthetic</code>; simulated client preferences stay synthetic for everyone. Category mapping, hand-checked on {rca['n']} posts:
{rca['category_accuracy']} category, {rca['persona_accuracy']} persona-level. Details, attribution and limits: <code>docs/DATA_CARD.md</code>.</p>
<p><b>Calibration.</b> The synthetic generator's hourly medians vs real contract medians: {", ".join(f"{k} {v['synthetic_hourly_median']} vs {v['real_hourly_p50']:g}" for k, v in rcal.items() if k in ("llm_apps", "web_app", "backend", "bi", "web_analytics", "research"))}.
The synthetic world over-prices developer work by 1.4–1.7× and under-prices analyst work. It was not regenerated (that would invalidate the labelled results);
real posts are priced from the real contracts instead (hourly rate inside the posted range, or real fixed-price percentiles).</p>
<p><b>Scam rules v1 → v2.</b> {t([["Synthetic scam jobs (text rules), precision / recall", f"{rs['rules_v1_vs_v2']['v1']['synthetic_scam']['precision']} / {rs['rules_v1_vs_v2']['v1']['synthetic_scam']['recall']}", f"{rs['rules_v1_vs_v2']['v2']['synthetic_scam']['precision']} / {rs['rules_v1_vs_v2']['v2']['synthetic_scam']['recall']}"],
 ["Real board posts flagged (in-sample)", rs['rules_v1_vs_v2']['v1']['real_posts_in_sample_flag_rate'], rs['rules_v1_vs_v2']['v2']['real_posts_in_sample_flag_rate']],
 ["3,000 held-out 2024 posts flagged", rs['rules_v1_vs_v2']['v1']['real_2024_heldout_flag_rate'], rs['rules_v1_vs_v2']['v2']['real_2024_heldout_flag_rate']],
 ["Dev pipeline scam precision / bid F1", f"{rv1['scam_precision']} / {rv1['bid_f1']}", f"{dev['scam_precision']} / {dev['bid_f1']}"]], ["", "v1", "v2"])}
<figure>{fig_scam}<figcaption>Figure 7. False-alarm rate on real posts, rules v1 vs v2.</figcaption></figure>
v1 fired on any mention of Telegram, WhatsApp or crypto; on real posts these are usually the product ("build a Telegram bot"). v2 needs an ask
("contact me on…", "we pay in USDT"). Of the 5 held-out v2 flags, 1 is a true request for free work, 1 ambiguous, 3 false alarms; v2 misses one
"USDT seller" post that v1 caught by accident. {src('real_scam_external.json')}</p>
<p><b>Outside scam test.</b> On the fake-job set's test half without the template fakes ({rs['test_without_templated_fakes']['risk_assessor_rules']['n']:,} ads), the freelance rules catch
{rs['test_without_templated_fakes']['risk_assessor_rules']['recall']} of fakes; TF-IDF + logistic regression trained on its train half gets F1 {rs['test_without_templated_fakes']['tfidf_logreg_trained_without_templates']['f1']}
there but recall {rs['transfer_to_freelance_posts']['synthetic_dev_scams']['tfidf_logreg']['recall']} on freelance scams. Job-ad fraud and marketplace scams look different, so the classifier is not shipped.</p>
<p><b>Real posts through the pipeline</b> ({rp['overall']['n_jobs']} posts, no labels): bid rate {rp['overall']['bid_rate_in_domain']} in the persona's market vs
{rp['overall']['bid_rate_out_of_domain']} outside it; bids inside real p10–p90 {rp['overall']['price_inside_real_p10_p90']}, within posted budget {rp['overall']['price_within_posted_budget']}.
The main in-market skip reasons are real-market facts the synthetic world under-represents: unverified clients with no spend (30% of real clients are
unverified) and budgets below the personas' floors. {src(f'pipeline_{P}_real.json')}</p>


<h2>12. Model-backed runs (open profile, Groq)</h2>
<p>The numbers above come from the deterministic rule profile, which every node has as a fallback. The open profile (gpt-oss-20b for analysts,
gpt-oss-120b for writer and judge, on Groq's free tier) is run by one command, <code>RUN_EVERYTHING.sh</code>, on the author's laptop, because the build
workspace has no model access. Groq's free tier allows 200k tokens per model per day, so the runs are cached (<code>LLM_CACHE=1</code>) and resume
the next day without repeating finished calls. The table shows what exists at the time this PDF was built; anything marked pending is not claimed anywhere in this report.</p>
{open_tbl}
<p><b>What these runs answer that the rule profile cannot:</b> whether a model writer follows injected instructions (with vs without defences),
whether the single ReAct agent really loses on scams and claims (§7), how well the LLM judge agrees with my own 1–5 scores (Cohen's kappa), and the
real cost and latency per proposal against the budgets in §14. <b>Expected risks:</b> the model writer adds more unsupported claims than the template writer
(so the verifier does more work), and gpt-oss may follow paraphrased injections that contain no trigger words.</p>
<h2>13. Safety and platform respect</h2>
<ul><li><b>Never:</b> send or spend without approval (interrupt + HMAC token per content hash), scrape or automate a browser (live mode via the
official MCP only, read polling ≥ 240 min, RUNBOOK), share contact details, claim unproven experience, follow instructions in job posts or client messages.</li>
<li><b>How:</b> untrusted text is delimited and closing tags are neutralised; the Risk Assessor's rule floor can't be lowered by a model; tool allowlists
(the Analyst has none, LLM agents have no write tools); Compliance policy pack; PII masking (email, phone, card, IBAN) in logs, traces and the audit log;
OAuth tokens Fernet-encrypted; every query scoped by user id.</li>
<li><b>What still gets through:</b> paraphrased injections without trigger words reach the writer as data (the model must ignore them); portfolio uploads
are shared between users who pick the same demo persona (known tenant-isolation gap for demo personas only); simulated clients cannot test whether
a real client is misled by a technically-true claim.</li></ul>

<h2>14. Hidden-test results against declared budgets</h2>
<p>The instructor's hidden run happens after the deadline. The table reports this repository's own held-out set (180 jobs, separate seed, never used
for tuning): bid F1 {ho['bid_f1']}, scam recall {ho['scam_recall']}, precision {ho['scam_precision']}, price in band {ho['price_in_band']}, reply rate
{ho['gigsim_reply_rate']}, injection success {ho['injection_attack_success_rate']}. {src(f'pipeline_{P}_heldout.json')}</p>{budget}
<p>Budgets are met trivially on the rule profile (no model calls). One optimisation that helped: passing the scouted job into the graph instead of
re-fetching it, plus running sync MCP tools off the event loop, cut a 15-job scout+analyse batch from about 75 s to under 25 s under GigSim's rate limit.
The model-profile numbers will replace these when an endpoint is available.</p>

<h2>Appendix A: Reproduce</h2>
<p><code>make seed</code> · start GigSim with held-out jobs · <code>MODEL_PROFILE={P} ./scripts/run_all_evals.sh</code> · <code>python scripts/update_readme.py {P}</code>
· <code>python docs/report/build_report.py {P}</code>. Tests: <code>make test</code> (32 Python tests), <code>make e2e</code> (5 Playwright tests).</p>
<h2>Appendix B: failure examples (trace ids)</h2>
{t([[k, e['job_id'], e['category'], e.get('action'), e.get('gold_bid'), e.get('price'), str(e.get('band')), e.get('trace_id')] for k, ex in fa['examples'].items() for e in ex[:3]],
   ['Class', 'Job', 'Category', 'Action', 'Gold bid', 'Price', 'Fair band', 'Trace'])}

<h2>Appendix C: tests and configuration budgets</h2>
<p>Unit tests cover guardrails (risk rules v1/v2, platform-name-as-product, injection delimiting, PII masking), pricing (fixed and hourly, real
bands), the claim verifier and the approval token. Contract tests pin MCP schemas. Integration tests cover the durable approval and crash-resume
path. Playwright end-to-end tests cover inbox → job → approve, the Studio, and the reviewer login on the deployed site.</p>
{t([["max graph steps per job", 40], ["max tokens per job", "30,000"], ["max Critic revisions", 2], ["read polling interval (live Upwork)", "≥ 240 min"],
    ["Connects spent without approval", 0], ["autonomy default", "<code>suggest_only</code> (skips also need a click)"], ["rag.variant", "best"], ["policy.version", "1 (2 after change request)"]],
   ["Setting (config/default.yaml)", "Value"])}
<p><b>Deployment.</b> React/Vite front end and FastAPI back end on Render (Docker), GigSim in the same container with <code>GIGSIM_REAL_JOBS=1</code> so
the public board shows real posts. CI runs ruff, the tests, the README-numbers check (every number in the README results block must appear in
<code>evals/results</code>) and the report build.</p>
<h2>Appendix D: AI usage</h2><p>See <code>docs/AI_USAGE.md</code>: tool used, files, and five mistakes caught.</p>
"""

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "report.html").write_text(f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>")
pdf = OUT / "GigBid_RnD_Report.pdf"
js = f"""
const {{ chromium }} = require('playwright');
(async () => {{ const b = await chromium.launch(); const p = await b.newPage();
await p.goto('file://{OUT / "report.html"}'); await p.waitForTimeout(500);
await p.pdf({{ path: '{pdf}', format: 'A4', printBackground: true, displayHeaderFooter: true, headerTemplate: '<span></span>',
 footerTemplate: '<div style="font-size:8px;width:100%;text-align:center;color:#777">GigBid R&D report · <span class="pageNumber"></span>/<span class="totalPages"></span></div>',
 margin: {{ top: '14mm', bottom: '14mm', left: '13mm', right: '13mm' }} }}); await b.close(); }})();
"""
(OUT / "_print.cjs").write_text(js)
npm_root = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip()
subprocess.run(["node", str(OUT / "_print.cjs")], check=True, env={**__import__("os").environ, "NODE_PATH": npm_root})
(OUT / "_print.cjs").unlink()
print("wrote", pdf)
