"""V0 baseline: fixed 500-char chunks, dense top-k cosine on the whole job post."""
from rag.pipeline import RetrievalConfig

CONFIG = RetrievalConfig(name="v0", chunking="fixed", query="whole", retrieval="dense")
