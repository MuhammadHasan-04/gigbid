"""Repo ingestion through the official GitHub MCP server (A5: a third-party server we did not write).

Server: GitHub's remote MCP endpoint (https://api.githubcopilot.com/mcp/) over Streamable HTTP with a
personal access token (read-only, public_repo scope is enough). Trust rationale: docs/TOOLS.md.
Only two of its tools are allowed (allowlist below): `get_file_contents` and `search_repositories`.

python -m rag.ingest.github --owner <user> --persona <name>   -> data/runtime/uploads/<persona>/*.json
Without GITHUB_PERSONAL_ACCESS_TOKEN the persona's local repos folder is used instead.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os

from rag.ingest.loaders import UPLOAD_DIR

GITHUB_MCP_URL = os.getenv("GITHUB_MCP_URL", "https://api.githubcopilot.com/mcp/")
ALLOWED = {"get_file_contents", "search_repositories"}
CODE_FILES = ["requirements.txt", "pyproject.toml", "package.json", "src/main.py", "main.py", "app.py"]


async def _tools():
    from langchain_mcp_adapters.client import MultiServerMCPClient
    tok = os.environ["GITHUB_PERSONAL_ACCESS_TOKEN"]
    client = MultiServerMCPClient({"github": {"transport": "streamable_http", "url": GITHUB_MCP_URL,
                                              "headers": {"Authorization": f"Bearer {tok}"}}})
    return {t.name: t for t in await client.get_tools() if t.name in ALLOWED}


async def fetch_repos(owner: str, limit: int = 10) -> list[tuple[str, str, str]]:
    tools = await _tools()
    found = json.loads(await tools["search_repositories"].ainvoke({"query": f"user:{owner} fork:false", "perPage": limit}))
    out = []
    for repo in found.get("items", [])[:limit]:
        name = repo["name"]

        async def get(path):
            try:
                r = await tools["get_file_contents"].ainvoke({"owner": owner, "repo": name, "path": path})
                return r if isinstance(r, str) else json.dumps(r)
            except Exception:
                return ""
        readme = await get("README.md")
        code = "\n".join([await get(p) for p in CODE_FILES])[:20000]
        if readme or code:
            out.append((name, readme, code))
    return out


def save(persona: str, repos: list[tuple[str, str, str]]) -> int:
    d = UPLOAD_DIR / persona
    d.mkdir(parents=True, exist_ok=True)
    for name, readme, code in repos:
        (d / f"gh-{name}.json").write_text(json.dumps({"evidence_id": f"{persona}:upload:gh-{name}", "title": name,
                                                       "text": readme + "\n\n" + code[:6000], "project_id": f"gh-{name}",
                                                       "source": "github-mcp"}))
    return len(repos)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", required=True)
    ap.add_argument("--persona", required=True)
    a = ap.parse_args()
    print("ingested", save(a.persona, asyncio.run(fetch_repos(a.owner))), "repos via GitHub MCP")
