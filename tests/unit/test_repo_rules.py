"""CI rules: no secrets in the repo, every prompt lives in agent/prompts, gigsim untouched (checked in CI by hash)."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECRET = re.compile(r"(gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|sk-lf-[a-z0-9-]{20,})")


def tracked():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    return [ROOT / f for f in out if (ROOT / f).is_file()]


def test_no_secrets_committed():
    hits = []
    for f in tracked():
        if f.suffix in {".png", ".pdf", ".jpg", ".gif", ".mp4", ".safetensors"}:
            continue
        try:
            if SECRET.search(f.read_text(errors="ignore")):
                hits.append(str(f))
        except Exception:
            pass
    assert not hits, f"possible secrets in {hits}"
    assert not (ROOT / ".env").exists() or ".env" not in [p.name for p in tracked()]


def test_prompts_live_in_prompt_files():
    """A model call must name a prompt file; inline system prompts in Python are not allowed."""
    bad = []
    for f in (ROOT / "agent").rglob("*.py"):
        t = f.read_text()
        if re.search(r'"role":\s*"system",\s*"content":\s*"[A-Za-z]', t) or re.search(r'You are (the|a) [A-Z]\w+', t):
            bad.append(str(f))
    assert not bad, bad
    names = set(re.findall(r'structured\(\s*"\w+",\s*"(\w+)"', "".join(p.read_text() for p in ROOT.rglob("*.py") if ".venv" not in str(p))))
    for n in names:
        assert (ROOT / "agent" / "prompts" / f"{n}.md").exists(), n


def test_every_prompt_is_versioned():
    for f in (ROOT / "agent" / "prompts").glob("*.md"):
        if f.name == "README.md":
            continue
        t = f.read_text()
        assert t.startswith("version:") and "## system" in t and "## user" in t, f.name
