import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MODEL_PROFILE", "heuristic")
os.environ.setdefault("TRACE_DIR", str(ROOT / "data" / "runtime" / "test_traces"))
os.environ.setdefault("RUNTIME_DIR", str(ROOT / "data" / "runtime" / "test"))
