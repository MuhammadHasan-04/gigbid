"""V7 query: HyDE - retrieve with a hypothetical ideal proposal for the job."""
from rag.pipeline import RetrievalConfig

CONFIG = RetrievalConfig(name="v7", chunking="fixed", query="hyde", retrieval="dense")
