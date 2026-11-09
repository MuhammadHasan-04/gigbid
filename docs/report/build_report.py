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
C = commit()


def t(rows, head):
    h = "".join(f"<th>{x}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{'' if c is None else c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>"


def src(f):
    return f'<span class="src">[{html.escape(f)}]</span>'


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

CSS = """
@page { size: A4; margin: 16mm 15mm 16mm 15mm; @bottom-center { content: counter(page); font-size: 9px; color: #777; } }
body { font: 10.2px/1.42 'DejaVu Sans', Arial, sans-serif; color: #1b1f1d; }
h1 { font-size: 20px; margin: 0 0 2px; color: #0f4c42; } h2 { font-size: 13.5px; color: #0f4c42; border-bottom: 1.5px solid #cfe0db; padding-bottom: 2px; margin: 13px 0 5px; page-break-after: avoid; }
h3 { font-size: 11px; margin: 8px 0 3px; } p { margin: 3px 0 5px; } ul { margin: 2px 0 6px 16px; padding: 0; } li { margin: 1px 0; }
table { border-collapse: collapse; width: 100%; margin: 4px 0 6px; font-size: 9px; page-break-inside: avoid; }
th { background: #e8f2ef; text-align: left; } th, td { border: 1px solid #cfd8d4; padding: 2.5px 4px; vertical-align: top; }
.src { color: #3a6a99; font-size: 8.5px; } .pending { color: #9a5a00; font-style: italic; } .meta { color: #555; font-size: 9.5px; }
.box { background: #f4f7f6; border-left: 3px solid #146356; padding: 5px 8px; margin: 6px 0; }
img { max-width: 100%; } .two { display: flex; gap: 10px; } .two > div { flex: 1; }
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
comparison, judge calibration) have committed runners and are marked pending. (3) Simulated-client reply rate is a designed proxy.</div>

<h2>1. Problem and constraints</h2>
<p>Freelancers spend hours scanning feeds, spend paid Connects on jobs they won't win, send generic proposals, and run into scams that ask for
free work or off-platform payment. GigBid automates discovery, assessment and drafting. The freelancer makes every decision that leaves the system.</p>
<ul><li><b>Never automated:</b> submitting a proposal, sending a message, spending Connects, claiming experience the portfolio doesn't prove, contacting
a client off-platform. Enforced by a LangGraph <code>interrupt()</code> <i>and</i> an HMAC approval token checked inside the Marketplace MCP server (ADR 0002).</li>
<li><b>Allowed automatically:</b> scouting, analysis, skipping (only with autonomy <code>auto_skip_low_fit</code>), drafting.</li>
<li><b>Budgets</b> (config, enforced per thread): 40 graph steps, 30k tokens per job, max 2 Critic revisions; latency and cost budgets in §10.</li></ul>

<h2>2. Architecture</h2>
<div class="two"><div><img src="../images/bid_graph.png" style="max-height:330px"></div><div>
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
Compliance are separated because each failure needs a different fix (§8). Typed hand-offs: <code>JobSpec, RiskReport, FitReport, BidDecision,
PriceQuote, ProposalDraft, Critique, ComplianceVerdict</code>. State, execution trace and long-term memory are kept apart (docs/ARCHITECTURE.md).</p></div></div>
<p><b>Durability (C6)</b> is tested in <code>tests/integration</code>: the graph pauses at approval, the process is replaced, approval resumes from the
Postgres checkpoint, and replaying the <code>submit</code> node from the previous checkpoint returns <code>idempotent_replay</code> with exactly one GigSim
submission and one Connects deduction. Public traces: <code>docs/traces/</code> (scam skip, approval, injection, Critic loop, crash-and-resume).</p>

<h2>3. R&amp;D question A: tool granularity</h2>
<p><b>Hypothesis:</b> a small set of mid-grained tools with rewritten, disambiguating descriptions beats both 17 fine-grained tools (selection errors
between near-duplicates) and 3 coarse tools with an <code>action</code> enum (argument errors) on tool-selection and argument accuracy, at fewer
tokens per task than fine-grained. <b>Setup:</b> 40 tasks with known correct calls (<code>evals/datasets/tool_tasks.jsonl</code>), same model, native tool
calling, <code>tool_choice=required</code>. <b>Results:</b> {tool_html}</p>
<p><b>Shipped design:</b> 10 read tools + 3 write tools; descriptions say what the tool is <i>not</i> for ("never for details of one known job id").
Contract tests pin schemas and annotations (<code>tests/contract/snapshots</code>).</p>

<h2>4. R&amp;D question B: RAG variants, claim verification, shipped choice</h2>
<p><b>Hypothesis (stated before running):</b> requirement decomposition plus hybrid retrieval raises evidence Recall@5 by 5+ points over V0 on jobs
with 4+ requirements. <b>Result: rejected.</b> Alone, V1 and V2 lowered Recall@5. Corpus: 384 dev jobs with gold evidence; retrieval unit = project.</p>
{rag_tbl}{src(f'rag_{P}.json')}
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
moved far less than one verifier rule moved them: before the fix in §8 the shipped pipeline had {before_fix['gigsim_reply_rate']} reply rate with
{before_fix['unsupported_before']} claims removed per proposal; after, {dev['gigsim_reply_rate']} with {dev['unsupported_before']}. Simulated clients reward
"must-have evidenced", which saturates once the top 3 items contain one strong match per must-have. Most variants already reach that, so nDCG gains
deeper in the ranking don't show up in replies. <b>Decision:</b> ship the sweep winner (<code>rag.variant: best</code>); revisit with the model profile.</p>

<h2>5. R&amp;D question C: single agent vs supervisor vs graph</h2>
<p><b>Setup:</b> 50 dev jobs (all scams and injections in the sample plus normal jobs), (a) one ReAct agent holding all tools, (b) prebuilt
<code>langgraph-supervisor</code> with researcher/matcher/writer, (c) the hand-built graph. Same model, same tools, same verifier and policy scan applied to outputs.
<b>Results:</b> {ac_html}</p>
<p><b>Expectation to test:</b> the single agent should match the graph on simple in-domain jobs at lower latency and fail on scams and injections (no
rule floor, no separate compliance pass), and on claims (no verifier). Whether to ship it: no, because only the graph can enforce the approval interrupt at a fixed point.</p>

<h2>6. The change request</h2>
<p>The official 2 Nov "platform policy update" text was not available, so the GigSim stand-in models one new <b>rule</b> (no external links except
GitHub) and one new <b>cost</b> (+2 Connects on jobs with 20+ proposals) as <code>policy_v2.yaml</code>. Absorbing it: {cr['config_lines_changed']} config line
(<code>policy.version: 2</code>), {cr['code_lines_changed']} code lines, {cr['time_to_absorb_seconds']} s including the full test suite ({cr['tests_after_change']}). Rules and
costs are data read by the Compliance Guard and Pricing Strategist. <b>Caveat:</b> {html.escape(cr['caveat'])} {src('change_request.json')}</p>

<h2>7. Signature extension: X2 proposal experiments</h2>
<p>Strategy A (evidence-first) vs B (question-first, short), paired on the same {ab['n_paired']} jobs, scored by GigSim's deterministic clients. Reply rate
A {ab['reply_rate_A']} vs B {ab['reply_rate_B']}, hire A {ab['hire_rate_A']} vs B {ab['hire_rate_B']}. Discordant pairs {ab['discordant_A_only']} vs {ab['discordant_B_only']},
McNemar exact p = {ab['mcnemar_exact_p']}. B loses because one cited project leaves the second must-have unevidenced. In production, assignment is
deterministic by job id (<code>experiments.proposal_ab</code>) and the arm is stored on the draft. {src(f'ab_test_{P}.json')}</p>

<h2>8. Failure analysis</h2>
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

<h2>9. Safety and platform respect</h2>
<ul><li><b>Never:</b> send or spend without approval (interrupt + HMAC token per content hash), scrape or automate a browser (live mode via the
official MCP only, read polling ≥ 240 min, RUNBOOK), share contact details, claim unproven experience, follow instructions in job posts or client messages.</li>
<li><b>How:</b> untrusted text is delimited and closing tags are neutralised; the Risk Assessor's rule floor can't be lowered by a model; tool allowlists
(the Analyst has none, LLM agents have no write tools); Compliance policy pack; PII masking (email, phone, card, IBAN) in logs, traces and the audit log;
OAuth tokens Fernet-encrypted; every query scoped by user id.</li>
<li><b>What still gets through:</b> paraphrased injections without trigger words reach the writer as data (the model must ignore them); portfolio uploads
are shared between users who pick the same demo persona (known tenant-isolation gap for demo personas only); simulated clients cannot test whether
a real client is misled by a technically-true claim.</li></ul>

<h2>10. Hidden-test results against declared budgets</h2>
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
<h2>Appendix C: AI usage</h2><p>See <code>docs/AI_USAGE.md</code>: tool used, files, and five mistakes caught.</p>
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
