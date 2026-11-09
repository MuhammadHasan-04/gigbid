"""CI rule: every number in the README results tables must appear in a file under evals/results/."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
readme = (ROOT / "README.md").read_text()
block = readme.split("<!-- results:start -->")[1].split("<!-- results:end -->")[0] if "<!-- results:start -->" in readme else ""
nums = set(re.findall(r"(?<![\w.])\d+\.\d+(?![\w.])", block))
corpus = ""
for f in (ROOT / "evals" / "results").glob("*.json"):
    corpus += json.dumps(json.loads(f.read_text()))
for f in (ROOT / "evals" / "results").glob("*.csv"):
    corpus += f.read_text()
missing = [n for n in sorted(nums) if n not in corpus and n.rstrip("0").rstrip(".") not in corpus]
if missing:
    print("numbers in README results not found in evals/results:", missing)
    sys.exit(1)
print(f"ok: {len(nums)} README numbers traced to evals/results")
