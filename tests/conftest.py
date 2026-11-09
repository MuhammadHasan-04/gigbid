import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MODEL_PROFILE", "heuristic")
os.environ.setdefault("TRACE_DIR", str(ROOT / "data" / "runtime" / "test_traces"))
os.environ.setdefault("RUNTIME_DIR", str(ROOT / "data" / "runtime" / "test"))
# isolated GigSim state for tests (never the dev server's state file)
_STATE = Path("/tmp/gigbid_test_gigsim_state.json")
if _STATE.exists():
    _STATE.unlink()
os.environ["GIGSIM_STATE_FILE"] = str(_STATE)
os.environ.setdefault("GIGSIM_ERROR_RATE", "0")
os.environ.setdefault("GIGSIM_RPM", "100000")
import shutil  # noqa: E402

shutil.rmtree(os.environ["RUNTIME_DIR"], ignore_errors=True)  # fresh idempotency stores + audit logs per run
