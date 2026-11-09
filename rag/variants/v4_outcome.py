"""V4 ranking: boost projects cited by similar past proposals that won or got replies."""
from rag.pipeline import RetrievalConfig

CONFIG = RetrievalConfig(name="v4", chunking="fixed", query="whole", retrieval="dense", outcome_boost=0.5)
