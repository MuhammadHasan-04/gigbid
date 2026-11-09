"""Load any freelancer's portfolio folder (for people using the Portfolio MCP server outside GigBid).

Layout is free-form: every .md / .txt / .pdf file is one evidence item; a sub-folder that holds a
README.md is treated as a repo (README + source files). The project id is the file stem or
folder name.
"""
from __future__ import annotations

from pathlib import Path

from rag.ingest.loaders import Evidence
from rag.skills import tag_skills

CODE_EXT = {".py", ".ts", ".tsx", ".js", ".sql", ".r", ".ipynb", ".go", ".rs", ".java"}


def load_folder(root: Path) -> list[Evidence]:
    items: list[Evidence] = []
    persona = root.name
    repos = {p.parent for p in root.rglob("README.md") if p.parent != root}
    for repo in sorted(repos):
        readme = (repo / "README.md").read_text(errors="ignore")
        pid = repo.name
        items.append(Evidence(f"{persona}:readme:{pid}", persona, "readme", readme, pid, pid, tag_skills(readme), source=str(repo / "README.md")))
        code = "\n".join(f.read_text(errors="ignore")[:4000] for f in sorted(repo.rglob("*")) if f.suffix.lower() in CODE_EXT)[:20000]
        if code:
            items.append(Evidence(f"{persona}:code:{pid}", persona, "code", code, pid, pid, tag_skills(code, code=True), source=str(repo)))
    for f in sorted(root.rglob("*")):
        if not f.is_file() or any(r in f.parents for r in repos):
            continue
        if f.suffix.lower() in (".md", ".txt"):
            text = f.read_text(errors="ignore")
        elif f.suffix.lower() == ".pdf":
            from pypdf import PdfReader
            text = "\n".join(p.extract_text() or "" for p in PdfReader(f).pages)
        else:
            continue
        kind = "cv" if "cv" in f.stem.lower() or "resume" in f.stem.lower() else "case_study"
        items.append(Evidence(f"{persona}:{kind}:{f.stem}", persona, kind, text, f.stem, f.stem, tag_skills(text), source=str(f)))
    return items
