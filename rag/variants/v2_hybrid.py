"""V2 retrieval: BM25 + dense fused with reciprocal rank fusion (exact tool names)."""
from rag.pipeline import RetrievalConfig

CONFIG = RetrievalConfig(name="v2", chunking="fixed", query="whole", retrieval="hybrid")
