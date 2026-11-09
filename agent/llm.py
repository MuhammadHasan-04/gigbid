"""Model routing: every node's model comes from agent/config.yaml (route by node, never in code).

Providers speak the OpenAI-compatible chat API (Groq, OpenRouter, Together, Ollama, vLLM).
`heuristic` is a deterministic, rule-based stand-in used offline, in CI and as the last-resort
fallback; each node supplies its own heuristic so the graph still completes when every model
endpoint is down (degraded mode is visible in the trace as provider=heuristic).
"""
from __future__ import annotations

import contextvars
import json
import os
import re
import time
from pathlib import Path
from typing import Callable, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from agent import settings, tracing

T = TypeVar("T", bound=BaseModel)
PROMPTS = Path(__file__).resolve().parent / "prompts"

BASE_URLS = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "together": ("https://api.together.xyz/v1", "TOGETHER_API_KEY"),
    # Google Gemini through its OpenAI-compatible endpoint (paid/proprietary profile; cost is reported)
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
    "ollama": (os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") + "/v1", ""),
    "openai_compat": (os.getenv("OPENAI_COMPAT_BASE_URL", "http://localhost:8000/v1"), "OPENAI_COMPAT_API_KEY"),
}

# usage accumulator for the current graph step (nodes copy it into state for budgets)
_usage: contextvars.ContextVar[dict | None] = contextvars.ContextVar("usage", default=None)


class BudgetExceeded(RuntimeError):
    pass


def start_usage() -> dict:
    u = {"tokens": 0, "usd": 0.0, "calls": 0, "providers": []}
    _usage.set(u)
    return u


def _add_usage(tokens: int, usd: float, provider: str):
    u = _usage.get()
    if u is not None:
        u["tokens"] += tokens
        u["usd"] += usd
        u["calls"] += 1
        u["providers"].append(provider)


def load_prompt(name: str) -> tuple[str, str]:
    """Prompts are versioned markdown files: front-matter `version:` then `## system` / `## user`."""
    text = (PROMPTS / f"{name}.md").read_text()
    m = re.search(r"^version:\s*(\S+)", text, re.M)
    version = m.group(1) if m else "0"
    sys_part = text.split("## system", 1)[1].split("## user", 1)[0].strip()
    user_part = text.split("## user", 1)[1].strip()
    return version, sys_part + "\n\n" + "\x00" + user_part


def render(name: str, **vars) -> tuple[str, str, str]:
    version, both = load_prompt(name)
    system, user = both.split("\x00")
    if defence_disabled():
        system = "\n".join(l for l in system.splitlines() if "security rule" not in l.lower())
    for k, v in vars.items():
        user = user.replace("{{" + k + "}}", v if isinstance(v, str) else json.dumps(v, default=str))
        system = system.replace("{{" + k + "}}", v if isinstance(v, str) else json.dumps(v, default=str))
    return version, system.strip(), user


def defence_disabled() -> bool:
    """Only for the injection-defence ablation (evals/runners/pipeline_eval.py --no-defence)."""
    return os.getenv("GIGBID_DISABLE_DEFENCE") == "1"


def untrusted(label: str, text: str) -> str:
    """Delimit untrusted marketplace text. Closing tags inside the text are neutralised."""
    if defence_disabled():
        return text
    clean = re.sub(r"</?\s*(untrusted|job_post|client_message|system)[^>]*>", "[tag removed]", text, flags=re.I)
    return f"<untrusted_{label}>\n{clean}\n</untrusted_{label}>"


def node_spec(node: str) -> tuple[dict, dict]:
    cfg = settings.get("models")
    prof = cfg["profiles"][cfg["profile"]]
    spec = (prof.get("nodes") or {}).get(node) or prof["default"]
    return spec, prof.get("fallback", {"provider": "heuristic", "model": "rules-v1"})


def provider_available(spec: dict) -> bool:
    p = spec["provider"]
    if p == "heuristic":
        return True
    if p in ("ollama", "openai_compat"):
        return True
    return bool(os.getenv(BASE_URLS[p][1]))


def _price(spec: dict, tin: int, tout: int) -> float:
    prices = settings.get("models.prices", {})
    pin, pout = prices.get(f"{spec['provider']}:{spec['model']}", [0.0, 0.0])
    return (tin * pin + tout * pout) / 1e6


def _chat(spec: dict, system: str, user: str, json_mode: bool, max_tokens: int) -> tuple[str, int, int]:
    base, key_env = BASE_URLS[spec["provider"]]
    headers = {"Authorization": f"Bearer {os.getenv(key_env, 'none')}"} if key_env else {}
    body = {"model": spec["model"], "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": spec.get("temperature", 0.2), "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if spec["provider"] == "gemini":
        body.setdefault("reasoning_effort", spec.get("reasoning_effort", "low"))
    if spec["provider"] == "groq" and "gpt-oss" in spec["model"]:
        body["reasoning_effort"] = spec.get("reasoning_effort", "low")
    timeout = settings.get("models.timeout_seconds", 45)
    last = None
    for attempt in range(settings.get("models.max_retries", 2) + 1):
        try:
            r = httpx.post(f"{base}/chat/completions", json=body, headers=headers, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                wait = float(r.headers.get("retry-after", 2 ** attempt))
                time.sleep(min(wait, 20))
                last = RuntimeError(f"{r.status_code}: {r.text[:200]}")
                continue
            r.raise_for_status()
            d = r.json()
            u = d.get("usage", {})
            return d["choices"][0]["message"]["content"] or "", u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
        except (httpx.HTTPError, KeyError) as e:
            last = e
            time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"model call failed: {last}")


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.M).strip()
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


def structured(node: str, prompt: str, schema: type[T], heuristic: Callable[[], T], max_tokens: int = 1200,
               **vars) -> T:
    """Run a node's prompt and parse into `schema`. Falls back: model -> fallback model -> heuristic."""
    spec, fallback = node_spec(node)
    version, system, user = render(prompt, schema=json.dumps(schema.model_json_schema()), **vars)
    for s in [spec, fallback]:
        if s["provider"] == "heuristic" or not provider_available(s):
            continue
        t0 = time.time()
        try:
            text, tin, tout = _chat(s, system, user, json_mode=True, max_tokens=max_tokens)
            obj = schema.model_validate(_parse_json(text))
            usd = _price(s, tin, tout)
            _add_usage(tin + tout, usd, s["provider"])
            tracing.emit("llm", prompt, provider=s["provider"], model=s["model"], prompt_version=version,
                         tokens_in=tin, tokens_out=tout, usd=usd, latency_s=round(time.time() - t0, 3))
            return obj
        except (RuntimeError, ValidationError, json.JSONDecodeError, ValueError) as e:
            tracing.emit("llm_error", prompt, provider=s["provider"], model=s["model"], error=str(e)[:300])
    t0 = time.time()
    obj = heuristic()
    _add_usage(0, 0.0, "heuristic")
    tracing.emit("llm", prompt, provider="heuristic", model="rules-v1", prompt_version=version,
                 tokens_in=0, tokens_out=0, usd=0.0, latency_s=round(time.time() - t0, 4))
    return obj


def text(node: str, prompt: str, heuristic: Callable[[], str], max_tokens: int = 900, **vars) -> str:
    spec, fallback = node_spec(node)
    version, system, user = render(prompt, **vars)
    for s in [spec, fallback]:
        if s["provider"] == "heuristic" or not provider_available(s):
            continue
        t0 = time.time()
        try:
            out, tin, tout = _chat(s, system, user, json_mode=False, max_tokens=max_tokens)
            usd = _price(s, tin, tout)
            _add_usage(tin + tout, usd, s["provider"])
            tracing.emit("llm", prompt, provider=s["provider"], model=s["model"], prompt_version=version,
                         tokens_in=tin, tokens_out=tout, usd=usd, latency_s=round(time.time() - t0, 3))
            return out.strip()
        except RuntimeError as e:
            tracing.emit("llm_error", prompt, provider=s["provider"], error=str(e)[:300])
    out = heuristic()
    _add_usage(0, 0.0, "heuristic")
    tracing.emit("llm", prompt, provider="heuristic", model="rules-v1", prompt_version=version, tokens_in=0, tokens_out=0,
                 usd=0.0, latency_s=0.0)
    return out
