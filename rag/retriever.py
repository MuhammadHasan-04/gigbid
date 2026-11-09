"""Factory: the variant used in production is chosen by config (rag.variant), never hard-coded."""
from __future__ import annotations

from functools import lru_cache

from agent import settings
from rag.ingest.loaders import load_persona
from rag.pipeline import Retriever
from rag.variants import get


@lru_cache(maxsize=16)
def _cached(persona: str, variant: str, version: int) -> Retriever:
    return Retriever(persona, get(variant))


_versions: dict[str, int] = {}


def get_retriever(persona: str, variant: str | None = None) -> Retriever:
    return _cached(persona, variant or settings.get("rag.variant", "best"), _versions.get(persona, 0))


def reindex(persona: str) -> int:
    """Incremental re-index after the user adds work in the UI: bump the version, rebuild lazily."""
    _versions[persona] = _versions.get(persona, 0) + 1
    return len(load_persona(persona))
