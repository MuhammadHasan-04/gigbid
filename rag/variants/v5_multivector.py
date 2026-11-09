"""V5 indexing: summary / README / code indexed as separate vectors, returned as one project."""
from rag.pipeline import RetrievalConfig

CONFIG = RetrievalConfig(name="v5", chunking="structural", query="whole", retrieval="dense", multi_vector=True)
