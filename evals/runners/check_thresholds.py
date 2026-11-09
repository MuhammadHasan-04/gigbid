"""CI gate: fail if unsupported claims rise or bid-or-skip F1 drops past the thresholds in evals/thresholds.yaml."""
import json
import sys
from pathlib import Path

import yaml

th = yaml.safe_load((Path(__file__).resolve().parents[1] / "thresholds.yaml").read_text())
o = json.load(open(sys.argv[1]))["overall"]["overall"]
fails = []
if o["bid_f1"] < th["min_bid_f1"]:
    fails.append(f"bid F1 {o['bid_f1']} < {th['min_bid_f1']}")
if (o["unsupported_after"] or 0) > th["max_unsupported_after"]:
    fails.append(f"unsupported claims after verification {o['unsupported_after']} > {th['max_unsupported_after']}")
if (o["scam_recall"] or 0) < th["min_scam_recall"]:
    fails.append(f"scam recall {o['scam_recall']} < {th['min_scam_recall']}")
if o["injection_attack_success_rate"] > th["max_injection_success"]:
    fails.append(f"injection success {o['injection_attack_success_rate']} > {th['max_injection_success']}")
if o["errors"] > th["max_errors"]:
    fails.append(f"{o['errors']} graph errors")
print("thresholds:", th)
print("smoke:", {k: o[k] for k in ("bid_f1", "unsupported_after", "scam_recall", "injection_attack_success_rate", "errors")})
if fails:
    print("FAIL:", "; ".join(fails))
    sys.exit(1)
print("PASS")
