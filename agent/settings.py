"""Config loader: agent/config.yaml + environment overrides (GIGBID__A__B=value)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal .env loader (no extra dependency). Real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.split(" #", 1)[0].strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)


_load_dotenv()
CONFIG_PATH = Path(os.getenv("GIGBID_CONFIG", ROOT / "agent" / "config.yaml"))


def _coerce(v: str) -> Any:
    try:
        return yaml.safe_load(v)
    except Exception:
        return v


@lru_cache(maxsize=1)
def config() -> dict:
    cfg = yaml.safe_load(CONFIG_PATH.read_text())
    for k, v in os.environ.items():
        if k.startswith("GIGBID__"):
            path = k[8:].lower().split("__")
            cur = cfg
            for p in path[:-1]:
                cur = cur.setdefault(p, {})
            cur[path[-1]] = _coerce(v)
    if os.getenv("MODEL_PROFILE"):
        cfg["models"]["profile"] = os.environ["MODEL_PROFILE"]
    if os.getenv("MARKETPLACE_MODE"):
        cfg["marketplace"]["mode"] = os.environ["MARKETPLACE_MODE"]
    if os.getenv("POLICY_VERSION"):
        cfg["policy"]["version"] = int(os.environ["POLICY_VERSION"])
    return cfg


def reload() -> dict:
    config.cache_clear()
    return config()


def get(path: str, default: Any = None) -> Any:
    cur: Any = config()
    for p in path.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def policy() -> dict:
    v = get("policy.version", 1)
    return yaml.safe_load((ROOT / get("policy.dir") / f"policy_v{v}.yaml").read_text())
