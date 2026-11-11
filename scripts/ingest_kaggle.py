"""Build GigBid's real-data layer from the six Kaggle datasets allowed for the assignment.

    python scripts/ingest_kaggle.py            # downloads (kagglehub, cached) and writes data/real/

Raw files are NOT committed (size, and one dataset has no stated licence). Only derived, small
artefacts go to data/real/, each record tagged with `source` ("real" or "synthetic") and the
dataset it came from. See docs/DATA_CARD.md for selection, preprocessing, licences and limits.

| dataset (Kaggle ref)                                         | used for                                   | output                          |
|--------------------------------------------------------------|--------------------------------------------|---------------------------------|
| ahmedmyalo/upwork-freelance-jobs-60k (Apache 2.0)            | real job posts + their clients' stats      | jobs_real.json.gz, clients_real.json |
| asaniczka/freelance-contracts-dataset-1-3-million-entries (ODC-By) | awarded contract values, hourly rates | market_real.json                |
| asaniczka/upwork-job-postings-dataset-2024-50k-records (ODC-By)    | 2024 posted budgets / hourly ranges  | market_real.json, demand_real.json |
| asaniczka/all-jobs-on-upwork-200k-plus (ODC-By)              | 2024 weekly demand per category            | demand_real.json                |
| sarveshchhetri/freelancer-success-earnings-and-churn-prediction (Apache 2.0, synthetic) | peer benchmarks for the personas | freelancer_benchmarks.json |
| adityammantri/trial-1 "Fake-Job-Posting-Detection" (licence: unknown) | external scam-detection test only (evals/runners/real_data_eval.py); nothing redistributed | – |
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "data" / "real"

DATASETS = {
    "jobs60k": ("ahmedmyalo/upwork-freelance-jobs-60k", "Final_Upwork_Dataset.csv", "Apache 2.0"),
    "contracts": ("asaniczka/freelance-contracts-dataset-1-3-million-entries", "contracts.csv", "ODC-By 1.0"),
    "jobs50k": ("asaniczka/upwork-job-postings-dataset-2024-50k-records", "upwork-jobs.csv", "ODC-By 1.0"),
    "jobs200k": ("asaniczka/all-jobs-on-upwork-200k-plus", "all_upwork_jobs_*.csv", "ODC-By 1.0"),
    "freelancers": ("sarveshchhetri/freelancer-success-earnings-and-churn-prediction", "freelancer_gig_success_dataset.csv", "Apache 2.0"),
    "fakejobs": ("adityammantri/trial-1", "processed_labeled_dataset_without_encoding.xlsx", "Unknown (not stated by the author)"),
}

# ----------------------------------------------------------------------------- category mapping
# Out-of-domain markers are checked on the title and the first three skill tags only (strong signal);
# domain rules then run over title + tags + description, in this order (first match wins).
OOD = [r"wordpress", r"\bphp\b", r"laravel", r"\bunity\b", r"\b3d\b", r"logo", r"video edit", r"\bseo\b", r"solidity",
       r"blockchain", r"\bnft\b", r"\bswift\b", r"\bios\b", r"android", r"kotlin", r"flutter", r"salesforce", r"lead gen",
       r"social media", r"cold call", r"virtual assistant", r"data entry", r"copywrit", r"graphic design", r"illustrat",
       r"animation", r"marketing", r"facebook ad", r"google ads", r"instagram", r"tiktok", r"youtube", r"wix", r"squarespace",
       r"webflow", r"bubble\.io", r"translation", r"transcription", r"voice over", r"bookkeep", r"appointment setter",
       r"telemarket", r"email marketing", r"\bgame\b", r"\bc\+\+\b", r"embedded", r"\bc#\b", r"\.net\b", r"\bjava\b"]
OOD_DESC = [r"sharepoint", r"project manag", r"wordpress", r"\bphp\b", r"shopify theme design", r"\bseo\b"]
OOD += [r"market research", r"\bsales\b", r"quoting", r"journalis", r"writing", r"instructor", r"tutor", r"teacher",
        r"grant", r"autocad", r"\bcad\b", r"prestashop", r"powerapps", r"scrap(e|ing)", r"data extraction", r"data mining",
        r"data collection", r"assessment", r"lead list", r"ui/ux", r"figma", r"ux design", r"user experience", r"poshmark", r"amazon (ppc|account|seller|fba)",
        r"pay per click", r"wcag", r"accessibility", r"high ?level", r"klaviyo", r"letters", r"smart contract", r"tokeni[sz]", r"\bcrm\b", r"zapier", r"make\.com", r"sharepoint", r"project manag", r"elixir", r"\bruby\b", r"rails", r"\bgo(lang)?\b developer", r"weebly", r"jquery", r"\bcss\b", r"\bhtml\b"]
RULES: list[tuple[str, list[str]]] = [
    ("llm_apps", [r"\bllm", r"\bgpt", r"chatgpt", r"openai", r"langchain", r"\brag\b", r"chatbot", r"chat bot", r"generative ai",
                  r"prompt engineer", r"large language", r"\bai agent", r"llama", r"hugging ?face", r"vector database"]),
    ("vision", [r"computer vision", r"opencv", r"\byolo", r"object detection", r"image recognition", r"image classification",
                r"image segmentation", r"face recognition", r"image processing", r"\bocr\b"]),
    ("nlp", [r"\bnlp\b", r"natural language", r"sentiment", r"text classification", r"named entity", r"spacy", r"text mining"]),
    ("recsys", [r"recommend(ation|er) (system|engine)", r"recommender"]),
    ("mlops", [r"mlops", r"model deploy", r"sagemaker", r"mlflow", r"kubeflow", r"deploy (a |the |my )?(ml|machine learning) model"]),
    ("forecasting", [r"forecast", r"time[ -]series"]),
    ("classical_ml", [r"machine learning", r"\bml\b", r"predictive model", r"scikit", r"xgboost", r"deep learning",
                      r"tensorflow", r"pytorch", r"neural network", r"data scien", r"\bai model", r"classification model"]),
    ("bi", [r"power ?bi", r"tableau", r"looker studio", r"data studio", r"data visuali", r"(kpi|analytics|reporting|sales|data) dashboards?"]),
    ("analytics_eng", [r"\bdbt\b", r"snowflake", r"bigquery", r"\betl\b", r"data pipeline", r"data warehouse", r"airflow",
                       r"redshift", r"data engineer"]),
    ("web_analytics", [r"google analytics", r"\bga4\b", r"tag manager", r"\bgtm\b", r"conversion tracking", r"mixpanel"]),
    ("product_analytics", [r"a/b test", r"ab test", r"cohort", r"product analytic", r"amplitude", r"retention analysis"]),
    ("research", [r"survey data", r"survey analy", r"questionnaire", r"\bspss\b", r"statistical analysis", r"\bstata\b", r"\br programming\b", r"\brstudio\b", r"biostat"]),
    ("spreadsheet", [r"excel", r"google sheets", r"spreadsheet", r"\bvba\b", r"financial model"]),
    ("ecommerce", [r"shopify", r"woocommerce", r"magento", r"e-?commerce", r"stripe", r"checkout"]),
    ("mobile", [r"react native", r"mobile app"]),
    ("testing", [r"playwright", r"cypress", r"selenium", r"qa automation", r"end-to-end test", r"\bjest\b", r"test automation"]),
    ("realtime", [r"websocket", r"socket\.io", r"real-?time"]),
    ("api", [r"graphql", r"api integration", r"api development", r"rest api", r"\bapi\b"]),
    ("backend", [r"django", r"node\.?js", r"express", r"nestjs", r"fastapi", r"flask", r"back-?end", r"postgres", r"mongodb"]),
    ("web_app", [r"react", r"next\.?js", r"vue", r"angular", r"typescript", r"full[ -]?stack", r"web app", r"saas",
                 r"javascript", r"web develop", r"front-?end"]),
    ("data_misc", [r"data analy", r"\bsql\b", r"python", r"data visuali", r"pandas"]),  # resolved below
]
PERSONA_OF = {
    **{c: "ai_ml" for c in ("llm_apps", "classical_ml", "vision", "nlp", "mlops", "recsys")},
    **{c: "fullstack" for c in ("web_app", "backend", "realtime", "ecommerce", "api", "testing", "mobile")},
    **{c: "data_analyst" for c in ("bi", "analytics_eng", "product_analytics", "web_analytics", "spreadsheet", "forecasting", "research")},
}


def categorize(title: str, tags: list[str], desc: str = "") -> str:
    head = (title + " | " + " | ".join(tags[:3])).lower()
    if any(re.search(p, head) for p in OOD):
        return "out_of_domain"
    # pass 1: title + skill tags (what the client chose to label the job with); pass 2: the description
    text = (title + " | " + " | ".join(tags)).lower()
    for cat, pats in RULES:
        if any(re.search(p, text) for p in pats):
            if cat == "data_misc":
                return "product_analytics" if "analy" in text else "out_of_domain"
            return cat
    if tags:  # the client tagged the job and none of the tags is ours -> not this market
        return "out_of_domain"
    # untagged posts: the description decides only when it is unambiguous (>= 2 distinct cues for one category)
    low = desc[:1500].lower()
    if any(re.search(p, low) for p in OOD_DESC):
        return "out_of_domain"
    hits = {cat: sum(bool(re.search(p, low)) for p in pats) for cat, pats in RULES if cat != "data_misc"}
    best = max(hits, key=hits.get) if hits else None
    return best if best and hits[best] >= 2 else "out_of_domain"


# Upwork skill tags -> GigBid skill vocabulary (gigsim/world.py SKILLS); unmapped tags stay as tags only
TAG_MAP = {
    "python": "Python", "pytorch": "PyTorch", "tensorflow": "TensorFlow", "scikit-learn": "scikit-learn", "xgboost": "XGBoost",
    "langchain": "LangChain", "openai api": "OpenAI API", "chatgpt": "OpenAI API", "gpt-3": "OpenAI API", "gpt-4": "OpenAI API",
    "computer vision": "computer vision", "opencv": "OpenCV", "natural language processing": "NLP", "nlp": "NLP",
    "spacy": "spaCy", "hugging face": "Hugging Face Transformers", "docker": "Docker", "fastapi": "FastAPI",
    "amazon sagemaker": "AWS SageMaker", "apache airflow": "Airflow", "prompt engineering": "prompt engineering",
    "javascript": "JavaScript", "typescript": "TypeScript", "react": "React", "reactjs": "React", "next.js": "Next.js",
    "vue.js": "Vue", "node.js": "Node.js", "expressjs": "Express", "nestjs": "NestJS", "django": "Django", "flask": "Flask",
    "postgresql": "PostgreSQL", "mongodb": "MongoDB", "redis": "Redis", "graphql": "GraphQL", "restful api": "REST API",
    "api": "REST API", "api development": "REST API", "api integration": "REST API", "tailwind css": "Tailwind CSS",
    "stripe": "Stripe", "amazon web services": "AWS", "aws": "AWS", "websocket": "WebSockets", "jest": "Jest",
    "shopify": "Shopify", "wordpress": "WordPress", "react native": "React Native", "sql": "SQL", "microsoft excel": "Excel",
    "excel": "Excel", "microsoft power bi": "Power BI", "power bi": "Power BI", "tableau": "Tableau", "looker": "Looker",
    "pandas": "pandas", "dbt": "dbt", "snowflake": "Snowflake", "bigquery": "BigQuery", "google analytics": "Google Analytics 4",
    "a/b testing": "A/B testing", "statistics": "statistics", "r": "R", "etl": "ETL", "data cleaning": "data cleaning",
    "dashboard": "dashboard design", "google sheets": "Google Sheets", "swift": "Swift", "unity": "Unity",
    "solidity": "Solidity", "video editing": "video editing", "machine learning": "scikit-learn", "deep learning": "PyTorch",
    "data visualization": "dashboard design", "statistical analysis": "statistics", "time series analysis": "time series forecasting",
}

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
URL = re.compile(r"https?://\S+|www\.\S+")
PHONE = re.compile(r"\+?\d[\d\s().-]{8,}\d")


def scrub(text: str) -> str:
    """Remove direct identifiers that can appear in real job posts (emails, links, phone numbers)."""
    text = EMAIL.sub("[email removed]", text)
    text = URL.sub("[link removed]", text)
    return PHONE.sub("[phone removed]", text)


def money(x) -> float | None:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    s = re.sub(r"[^\d.]", "", str(x))
    try:
        return float(s) if s else None
    except ValueError:
        return None


def pct(xs: list[float], q: float) -> float | None:
    xs = sorted(x for x in xs if x is not None and x == x)
    if not xs:
        return None
    return round(xs[min(len(xs) - 1, int(q * (len(xs) - 1)))], 2)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(key: str) -> list[Path]:
    import kagglehub
    ref, pattern, _ = DATASETS[key]
    base = Path(kagglehub.dataset_download(ref))
    files = sorted(base.glob(pattern))
    if not files:
        raise FileNotFoundError(f"{ref}: no {pattern} in {base}")
    return files


# ----------------------------------------------------------------------------- builders
APPLICANTS = {"Less than 5": 3, "5 to 10": 7, "10 to 15": 12, "15 to 20": 17, "20 to 50": 35, "50+": 60}
DURATION = [("less than 1 month", 21), ("1 to 3 months", 60), ("3 to 6 months", 120), ("more than 6 months", 200)]


def build_jobs(manifest: dict, per_category: int = 60, ood: int = 240, seed: int = 11):
    import pandas as pd
    (f,) = fetch("jobs60k")
    d = pd.read_csv(f, low_memory=False)
    m = {"rows_read": len(d)}
    d = d.dropna(subset=["Job Title", "Description"])
    d = d[d["Description"].str.len() >= 150]
    d = d.drop_duplicates("Job_URL").drop_duplicates("Description")
    m["rows_after_clean_dedupe"] = len(d)
    rng = random.Random(seed)
    pools: dict[str, list] = defaultdict(list)
    for row in d.to_dict("records"):
        tags = [str(row.get(f"Category_{i}")) for i in range(1, 10) if str(row.get(f"Category_{i}")) not in ("nan", "None")]
        cat = categorize(str(row.get("Job Title")), tags, str(row["Description"]))
        pools[cat].append((row, tags))
    m["category_counts_all"] = {k: len(v) for k, v in sorted(pools.items())}
    jobs, clients = [], []
    for cat, rows in sorted(pools.items()):
        rng.shuffle(rows)
        for row, tags in rows[: (ood if cat == "out_of_domain" else per_category)]:
            title = str(row.get("Job Title")).strip()
            url = str(row.get("Job_URL"))
            jid = "real-" + hashlib.sha1(url.encode()).hexdigest()[:10]
            desc = scrub(str(row["Description"]).strip())
            mapped = []
            for t in tags:
                v = TAG_MAP.get(t.lower())
                if v and v not in mapped:
                    mapped.append(v)
            if str(row.get("Payment_type")) == "Hourly":
                lo, hi = money(row.get("Start_rate")), money(row.get("End_rate"))
                budget = {"type": "hourly", "min": lo or 0, "max": hi or lo or 0, "currency": "USD"}
            else:
                c = money(row.get("Job_Cost"))
                budget = {"type": "fixed", "min": c or 0, "max": c or 0, "currency": "USD"} if c else {"type": "unknown", "min": 0, "max": 0, "currency": "USD"}
            tl = str(row.get("Time_Limitation")).lower()
            dur = next((v for k, v in DURATION if k in tl), None)
            cid = "rc-" + jid[5:]
            spent = money(row.get("Spent($)"))
            rating = money(row.get("Rating"))
            fb = money(row.get("Feedback_Num"))
            verified = str(row.get("Payment_Situation")) == "Payment verified"
            connects = money(row.get("Connects_Num"))
            jobs.append({
                "job_id": jid, "title": title, "category": cat, "industry": "",
                "description": desc, "required_skills_public": mapped, "upwork_skill_tags": tags,
                "budget": budget, "duration_days": dur or 30, "client_id": cid, "screening_questions": [],
                "connects_cost": int(connects) if connects else 8 + 2 * (budget["max"] >= 500),
                "proposals_count": APPLICANTS.get(str(row.get("Applicants_Num")), 15),
                "experience_level": str(row.get("EX_level_demand")) if str(row.get("EX_level_demand")) != "nan" else None,
                "source": "real", "source_dataset": DATASETS["jobs60k"][0], "source_url": url,
                "posted_period": "2023-02/2023-03",
                # labels: nothing here is known for real posts except what the post itself states
                "_gold": {"requirements": mapped, "label_source": "Upwork skill tags mapped to GigBid vocabulary",
                          "scam_kinds": None, "injection": None, "hidden_need": None, "persona_hint": PERSONA_OF.get(cat),
                          "est_hours": None},
                "_synthetic_fields": ["industry(empty)"] + (["duration_days"] if not dur else []) + ([] if connects else ["connects_cost"]),
            })
            h = int(hashlib.sha256(cid.encode()).hexdigest()[:8], 16)
            r2 = random.Random(h)
            clients.append({
                "client_id": cid, "country": str(row.get("Client_Country")) if str(row.get("Client_Country")) != "nan" else None,
                "payment_verified": verified, "total_spent": spent or 0, "jobs_posted": None,
                "hires": int(fb) if fb else 0, "hire_rate": None, "avg_rating_given": rating,
                "enterprise": str(row.get("Enterprise_Client")) not in ("nan", "None", ""),
                "member_since": None, "freelancer_reviews": [], "source": "real", "source_dataset": DATASETS["jobs60k"][0],
                "_risky": None,
                # GigSim's simulated client needs hidden preferences; these are SYNTHETIC (seeded by client id)
                "_hidden": {"dislikes_generic_opening": r2.random() < 0.6, "prefers_concise": r2.random() < 0.5,
                            "budget_flex": round(r2.uniform(0.9, 1.25), 2), "base_reply": round(r2.uniform(-1.2, 0.2), 2)},
                "_hidden_source": "synthetic",
            })
    m["jobs_kept"] = len(jobs)
    m["category_counts_kept"] = dict(Counter(j["category"] for j in jobs))
    m["budget_types_kept"] = dict(Counter(j["budget"]["type"] for j in jobs))
    manifest["jobs60k"] = m
    return jobs, clients


def build_market(manifest: dict) -> tuple[dict, dict]:
    import pandas as pd
    # ---- awarded contracts
    (f,) = fetch("contracts")
    c = pd.read_csv(f, usecols=["job_title", "start_date", "total_paid", "hourly_rate", "end_date"])
    m = {"rows_read": len(c)}
    c["start_date"] = pd.to_datetime(c["start_date"], errors="coerce", format="mixed")
    c = c[(c.start_date >= "2015-01-01") & (c.start_date <= "2025-12-31")]
    c["category"] = [categorize(str(t), []) for t in c.job_title]
    hourly = c[c.hourly_rate > 0]
    fixed = c[c.hourly_rate.isna() & (c.total_paid > 0) & c.end_date.notna()]
    m.update(rows_in_date_range=len(c), hourly_contracts=len(hourly), fixed_completed_contracts=len(fixed))
    market: dict[str, dict] = {}
    for cat in sorted(set(c.category)):
        h = hourly[hourly.category == cat].hourly_rate.clip(upper=500).tolist()
        fx = fixed[fixed.category == cat].total_paid.clip(upper=100000).tolist()
        market[cat] = {"contracts": {"n_hourly": len(h), "hourly_p10": pct(h, .1), "hourly_p25": pct(h, .25), "hourly_p50": pct(h, .5),
                                     "hourly_p75": pct(h, .75), "hourly_p90": pct(h, .9),
                                     "n_fixed": len(fx), "fixed_p10": pct(fx, .1), "fixed_p25": pct(fx, .25), "fixed_p50": pct(fx, .5),
                                     "fixed_p75": pct(fx, .75), "fixed_p90": pct(fx, .9)}}
    manifest["contracts"] = m
    # ---- 2024 postings (50k with descriptions + 200k tracker), deduplicated by link
    frames = []
    for key in ("jobs50k", "jobs200k"):
        for fp in fetch(key):
            x = pd.read_csv(fp, usecols=["title", "link", "published_date", "is_hourly", "hourly_low", "hourly_high", "budget"], low_memory=False)
            x["src"] = key
            frames.append(x)
            manifest.setdefault(key, {}).setdefault("rows_read", 0)
            manifest[key]["rows_read"] += len(x)
    p = pd.concat(frames).drop_duplicates("link")
    p["published_date"] = pd.to_datetime(p.published_date, errors="coerce", utc=True, format="mixed")
    p = p[p.published_date.notna()]
    p["category"] = [categorize(str(t), []) for t in p.title]
    manifest["postings_2024"] = {"unique_postings": len(p), "from": str(p.published_date.min().date()), "to": str(p.published_date.max().date())}
    ph = p[p.hourly_low.fillna(0) > 0]
    pf = p[p.budget.fillna(0) > 0]
    for cat in sorted(set(p.category)):
        lo = ph[ph.category == cat].hourly_low.clip(upper=500).tolist()
        hi = ph[ph.category == cat].hourly_high.clip(upper=500).tolist()
        b = pf[pf.category == cat].budget.clip(upper=100000).tolist()
        market.setdefault(cat, {})["postings_2024"] = {"n": int((p.category == cat).sum()), "n_hourly": len(lo),
                                                       "hourly_low_p50": pct(lo, .5), "hourly_high_p50": pct(hi, .5),
                                                       "n_fixed": len(b), "budget_p25": pct(b, .25), "budget_p50": pct(b, .5),
                                                       "budget_p75": pct(b, .75)}
    # weekly demand per category (share of all postings that week)
    p["week"] = p.published_date.dt.strftime("%G-W%V")
    wk = p.groupby(["week", "category"]).size().unstack(fill_value=0)
    wk = wk[wk.sum(axis=1) >= 500]  # drop partial weeks at the edges
    demand = {"weeks": list(wk.index), "postings_per_week": [int(v) for v in wk.sum(axis=1)],
              "share": {cat: [round(v, 4) for v in (wk[cat] / wk.sum(axis=1)).tolist()] for cat in wk.columns},
              "source": [DATASETS["jobs50k"][0], DATASETS["jobs200k"][0]], "kind": "real"}
    return market, demand


def build_benchmarks(manifest: dict) -> dict:
    import pandas as pd
    (f,) = fetch("freelancers")
    d = pd.read_csv(f)
    manifest["freelancers"] = {"rows_read": len(d), "note": "third-party SYNTHETIC records (dataset tag 'synthetic'); used only as peer benchmarks"}
    out = {}
    for skill, g in d.groupby("primary_skill"):
        out[skill] = {"n": len(g), "hourly_p25": pct(g.hourly_rate_usd.tolist(), .25), "hourly_p50": pct(g.hourly_rate_usd.tolist(), .5),
                      "hourly_p75": pct(g.hourly_rate_usd.tolist(), .75),
                      "job_success_p50": pct(g.job_success_rate.tolist(), .5),
                      "avg_response_time_hrs_p50": pct(g.avg_response_time_hrs.tolist(), .5),
                      "earnings_12m_p50": pct(g.total_earnings_12m_usd.tolist(), .5)}
    hr = d.hourly_rate_usd.dropna()
    check = {"hourly_rate_max": float(hr.max()), "share_at_max": round(float((hr == hr.max()).mean()), 4),
             "hourly_p50_all": pct(hr.tolist(), .5),
             "verdict": "REJECTED for pricing: most rates sit at a hard cap and the median is ~10x the real contract median "
                        "(market_real.json); kept only to document the check"}
    return {"by_primary_skill": out, "quality_check": check, "used_by_gigbid": False,
            "kind": "synthetic (third-party)", "source": DATASETS["freelancers"][0]}


def calibration(market: dict) -> dict:
    """How far the stand-in's synthetic hourly medians (gigsim/generate.py CATEGORY_RATE) are from real contracts."""
    from gigsim.generate import CATEGORY_RATE
    rows = {}
    for cat, syn in CATEGORY_RATE.items():
        real = (market.get(cat) or {}).get("contracts", {})
        if real.get("hourly_p50") and real.get("n_hourly", 0) >= 30:
            rows[cat] = {"synthetic_hourly_median": syn, "real_hourly_p50": real["hourly_p50"], "n_real": real["n_hourly"],
                         "ratio_synthetic_to_real": round(syn / real["hourly_p50"], 2)}
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "datasets": {}}
    for k, (ref, pattern, lic) in DATASETS.items():
        files = fetch(k)
        manifest["datasets"][k] = {"kaggle_ref": ref, "url": f"https://www.kaggle.com/datasets/{ref}", "license": lic,
                                   "files": {p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)} for p in files}}
    jobs, clients = build_jobs(manifest)
    market, demand = build_market(manifest)
    bench = build_benchmarks(manifest)
    cal = calibration(market)
    with gzip.open(OUT / "jobs_real.json.gz", "wt", encoding="utf-8") as fh:
        json.dump(jobs, fh, ensure_ascii=False)
    (OUT / "clients_real.json").write_text(json.dumps(clients, ensure_ascii=False))
    (OUT / "market_real.json").write_text(json.dumps({"by_category": market, "kind": "real",
                                                      "source": [DATASETS["contracts"][0], DATASETS["jobs50k"][0], DATASETS["jobs200k"][0]]}, indent=1))
    (OUT / "demand_real.json").write_text(json.dumps(demand))
    (OUT / "freelancer_benchmarks.json").write_text(json.dumps(bench, indent=1))
    (OUT / "calibration.json").write_text(json.dumps(cal, indent=1))
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=1, default=str))
    print(json.dumps({k: v for k, v in manifest.items() if k != "datasets"}, indent=1, default=str))
    print("calibration:", json.dumps(cal, indent=1))


if __name__ == "__main__":
    main()
