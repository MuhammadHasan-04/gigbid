"""Portfolio loaders: PDF CVs, Markdown case studies, repo READMEs and code, reviews, past proposals.

Every evidence item carries metadata: persona, type, project, skills, date, client industry and,
for proposals, outcome. Repos are read from the local persona folder by default; when a GitHub
token is configured they are pulled through the GitHub MCP server instead (see github.py).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from rag.skills import tag_skills

ROOT = Path(__file__).resolve().parents[2]
PERSONA_DIR = ROOT / "data" / "personas"


@dataclass
class Evidence:
    evidence_id: str
    persona: str
    type: str  # cv | case_study | readme | code | review | proposal | upload
    text: str
    project_id: str | None = None
    title: str = ""
    skills: list[str] = field(default_factory=list)
    date: str | None = None
    industry: str | None = None
    outcome: str | None = None
    source: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha1(self.text.encode()).hexdigest()[:12]


def _projects(persona: str) -> dict[str, dict]:
    return {p["project_id"]: p for p in json.loads((PERSONA_DIR / persona / "projects.json").read_text())}


def load_cv(persona: str) -> list[Evidence]:
    from pypdf import PdfReader
    projects = _projects(persona)
    by_title = {p["title"].lower(): p for p in projects.values()}
    text = "\n".join(page.extract_text() or "" for page in PdfReader(PERSONA_DIR / persona / "cv.pdf").pages)
    text = re.sub(r"\s+\n", "\n", text)
    items = []
    bullets = [b.strip().replace("\n", " ") for b in text.split("•")[1:]]
    for i, b in enumerate(bullets):
        proj = next((p for t, p in by_title.items() if b.lower().startswith(t[:40])), None)
        items.append(Evidence(f"{persona}:cv:{i:02d}", persona, "cv", b, proj and proj["project_id"],
                              proj["title"] if proj else "CV entry", tag_skills(b), proj and str(proj["year"]),
                              proj and proj["industry"], source="cv.pdf"))
    header = text.split("•")[0]
    items.append(Evidence(f"{persona}:cv:summary", persona, "cv", header.strip(), None, "CV summary",
                          tag_skills(header), source="cv.pdf"))
    return items


def load_case_studies(persona: str) -> list[Evidence]:
    projects = _projects(persona)
    out = []
    for f in sorted((PERSONA_DIR / persona / "case_studies").glob("*.md")):
        p = projects.get(f.stem)
        txt = f.read_text()
        out.append(Evidence(f"{persona}:case:{f.stem}", persona, "case_study", txt, f.stem, p["title"] if p else f.stem,
                            tag_skills(txt), str(p["year"]) if p else None, p and p["industry"], source=str(f.relative_to(ROOT))))
    return out


def load_repos(persona: str, repos: list[tuple[str, str, str]] | None = None) -> list[Evidence]:
    """repos: optional list of (project_id, readme_text, code_text) fetched elsewhere (GitHub MCP)."""
    projects = _projects(persona)
    if repos is None:
        repos = []
        for d in sorted((PERSONA_DIR / persona / "repos").iterdir()):
            code = "\n".join(f.read_text() for f in sorted((d / "src").glob("*")))
            repos.append((d.name, (d / "README.md").read_text(), code))
    out = []
    for pid, readme, code in repos:
        p = projects.get(pid, {})
        out.append(Evidence(f"{persona}:readme:{pid}", persona, "readme", readme, pid, p.get("title", pid), tag_skills(readme),
                            str(p.get("year")), p.get("industry"), source=f"repos/{pid}/README.md"))
        out.append(Evidence(f"{persona}:code:{pid}", persona, "code", code, pid, p.get("title", pid), tag_skills(code, code=True),
                            str(p.get("year")), p.get("industry"), source=f"repos/{pid}/src"))
    return out


def load_reviews(persona: str) -> list[Evidence]:
    projects = _projects(persona)
    out = []
    for r in json.loads((PERSONA_DIR / persona / "reviews.json").read_text()):
        p = projects.get(r["project_id"], {})
        txt = f"Client review ({r['rating']}/5) for {p.get('title', '')}: {r['text']}"
        out.append(Evidence(f"{persona}:review:{r['review_id']}", persona, "review", txt, r["project_id"], p.get("title", ""),
                            tag_skills(txt), str(p.get("year")), p.get("industry"), source="reviews.json"))
    return out


def load_proposals(persona: str) -> list[Evidence]:
    out = []
    for line in (PERSONA_DIR / persona / "past_proposals.jsonl").read_text().splitlines():
        r = json.loads(line)
        out.append(Evidence(f"{persona}:proposal:{r['proposal_id']}", persona, "proposal", r["text"],
                            (r.get("cited_projects") or [None])[0], r["job_title"], r["requirements"], r["date"],
                            r["industry"], r["outcome"], source="past_proposals.jsonl"))
    return out


def load_persona(persona: str, include_proposals: bool = True) -> list[Evidence]:
    items = load_cv(persona) + load_case_studies(persona) + load_repos(persona) + load_reviews(persona)
    items += load_uploads(persona)
    if include_proposals:
        items += load_proposals(persona)
    return items


UPLOAD_DIR = ROOT / "data" / "runtime" / "uploads"


def load_uploads(persona: str) -> list[Evidence]:
    """User-added work from the UI (incremental re-indexing picks these up)."""
    d = UPLOAD_DIR / persona
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("*.json")):
        r = json.loads(f.read_text())
        out.append(Evidence(r["evidence_id"], persona, "upload", r["text"], r.get("project_id"), r.get("title", "Upload"),
                            tag_skills(r["text"]), r.get("date"), r.get("industry"), source=f"upload:{f.name}"))
    return out


PERSONAS = ["ai_ml", "fullstack", "data_analyst"]
