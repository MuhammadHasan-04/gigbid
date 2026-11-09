"""Check which configured model endpoints are reachable and which model ids exist (never prints keys).

python scripts/check_models.py
"""
import os

import httpx

from agent import llm, settings

for prov, (base, key_env) in llm.BASE_URLS.items():
    if key_env and not os.getenv(key_env):
        continue
    if prov in ("ollama", "openai_compat"):
        continue
    try:
        r = httpx.get(f"{base}/models", headers={"Authorization": f"Bearer {os.getenv(key_env, '')}"}, timeout=15)
        ids = [m.get("id") for m in r.json().get("data", [])] if r.status_code == 200 else []
        print(f"{prov}: HTTP {r.status_code}; {len(ids)} models")
        flash = [i for i in ids if "flash" in i.lower()]
        if flash:
            print("  flash models:", ", ".join(sorted(flash)))
    except Exception as e:
        print(f"{prov}: unreachable ({type(e).__name__}: {str(e)[:120]})")

prof = settings.get("models.profile")
spec, _ = llm.node_spec("writer")
print(f"profile={prof} writer={spec}")
try:
    out, tin, tout = llm._chat(spec, "Reply with the single word OK.", "ping", json_mode=False, max_tokens=20)
    print(f"test call OK: {out.strip()[:40]!r} tokens in/out {tin}/{tout}")
except Exception as e:
    print(f"test call failed: {str(e)[:300]}")
