"""V3 retrieval: cross-encoder reranking (bge-reranker-v2-m3) of the top 20 candidates."""
from rag.pipeline import RetrievalConfig

CONFIG = RetrievalConfig(name="v3", chunking="fixed", query="whole", retrieval="dense", rerank="bge")
