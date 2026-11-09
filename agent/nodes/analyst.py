"""Job Analyst: job post -> JobSpec (no MCP access; works only on the job it is handed)."""
from __future__ import annotations

import re

from agent import llm
from agent.handoffs import JobSpec
from rag.skills import all_skill_names, tag_skills

HIDDEN_NEED_CUES = {
    "documentation": ["not technical", "non-technical", "maintain this", "hand over", "handover"],
    "timezone": ["overlap", "time zone", "timezone", "new york", "est "],
    "deadline": ["investor demo", "end of the month", "asap", "urgent", "deadline"],
    "legacy_code": ["older system", "legacy", "nobody fully understands"],
    "data_privacy": ["health data", "privacy", "gdpr", "hipaa", "sensitive"],
}


def heuristic_spec(job: dict) -> JobSpec:
    text = f"{job['title']}. {job['description']}"
    reqs = tag_skills(text)
    for s in job.get("required_skills_public", []):
        if s not in reqs:
            reqs.append(s)
    low = text.lower()
    needs = [k for k, cues in HIDDEN_NEED_CUES.items() if any(c in low for c in cues)]
    deliverables = [s.strip() for s in re.split(r"(?<=[.!?])\s+", job["description"])
                    if re.search(r"\b(build|create|deliver|need|looking for|project)\b", s, re.I)][:3]
    b = job.get("budget", {})
    return JobSpec(job_id=job["job_id"], title=job["title"], deliverables=deliverables, requirements=reqs,
                   budget_min=b.get("min", 0), budget_max=b.get("max", 0), timeline_days=job.get("duration_days"),
                   screening_questions=job.get("screening_questions", []), hidden_needs=needs,
                   category=job.get("category"), industry=job.get("industry"))


def analyze(job: dict) -> JobSpec:
    spec = llm.structured(
        "analyst", "analyst", JobSpec, lambda: heuristic_spec(job), max_tokens=900,
        job=llm.untrusted("job_post", f"{job['title']}\n{job['description']}"),
        vocab=", ".join(all_skill_names()), budget=str(job.get("budget")),
        questions="; ".join(job.get("screening_questions", [])), job_id=job["job_id"])
    # the id, budget and questions come from the trusted API fields, not from the model
    b = job.get("budget", {})
    spec.job_id, spec.title = job["job_id"], job["title"]
    spec.budget_min, spec.budget_max = b.get("min", 0), b.get("max", 0)
    spec.screening_questions = job.get("screening_questions", [])
    spec.category, spec.industry = job.get("category"), job.get("industry")
    names = set(all_skill_names())
    spec.requirements = [r for r in dict.fromkeys(spec.requirements) if r in names or len(r) < 40][:10]
    return spec
