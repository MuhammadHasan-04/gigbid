"""V6 indexing: a generated context line is prepended to every chunk before embedding."""
from rag.pipeline import RetrievalConfig

CONFIG = RetrievalConfig(name="v6", chunking="fixed", query="whole", retrieval="dense", contextual=True)
