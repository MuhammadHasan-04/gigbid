"""V1 query: one retrieval per extracted requirement, merged with RRF."""
from rag.pipeline import RetrievalConfig

CONFIG = RetrievalConfig(name="v1", chunking="fixed", query="decompose", retrieval="dense")
