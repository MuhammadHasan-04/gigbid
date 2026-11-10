"""Embedding backends (open models only, in both profiles).

* wordllama  - WordLlama l2_supercat 256-d (open weights shipped inside the pip wheel; CPU, no download)
* ollama     - any Ollama embedding model, e.g. nomic-embed-text or bge-m3 (needs an Ollama service)
* openai_compat - an OpenAI-compatible /embeddings endpoint serving an open model (e.g. TEI, vLLM)
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np

CACHE = Path(__file__).resolve().parents[2] / "data" / "processed" / "emb_cache"


def _ensure_wordllama_tokenizer():
    # wordllama looks for the tokenizer in ~/.cache; copy the one shipped in the wheel (offline).
    import wordllama
    src = Path(wordllama.__file__).parent / "tokenizers"
    dst = Path.home() / ".cache" / "wordllama" / "tokenizers"
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.glob("*.json"):
        if not (dst / f.name).exists():
            (dst / f.name).write_bytes(f.read_bytes())


class Embedder:
    def __init__(self, spec: str | None = None):
        self.spec = spec or os.getenv("EMBEDDINGS", "wordllama")
        self._model = None
        self._mem: dict[str, np.ndarray] = {}

    @property
    def name(self) -> str:
        return self.spec

    def _load(self):
        if self._model is None and self.spec == "wordllama":
            _ensure_wordllama_tokenizer()
            from wordllama import WordLlama
            self._model = WordLlama.load(dim=256)
        return self._model

    def _embed_batch(self, texts: list[str]) -> np.ndarray:
        if self.spec == "wordllama":
            # small batches: wordllama pads each batch to its longest text, and large padded batches
            # cost ~100 MB of RSS that the allocator never returns (the free hosting tier has 512 MB)
            return np.asarray(self._load().embed(texts, norm=True, batch_size=8), dtype=np.float32)
        if self.spec.startswith("ollama:"):
            import httpx
            base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            r = httpx.post(f"{base}/api/embed", json={"model": self.spec.split(":", 1)[1], "input": texts}, timeout=120)
            r.raise_for_status()
            v = np.asarray(r.json()["embeddings"], dtype=np.float32)
        elif self.spec.startswith("openai_compat:"):
            import httpx
            base = os.environ["EMBEDDINGS_BASE_URL"]
            r = httpx.post(f"{base}/embeddings", json={"model": self.spec.split(":", 1)[1], "input": texts},
                           headers={"Authorization": f"Bearer {os.getenv('EMBEDDINGS_API_KEY', '')}"}, timeout=120)
            r.raise_for_status()
            v = np.asarray([d["embedding"] for d in r.json()["data"]], dtype=np.float32)
        else:
            raise ValueError(f"unknown embeddings backend {self.spec}")
        return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)

    def embed(self, texts: list[str]) -> np.ndarray:
        keys = [hashlib.sha1((self.spec + "|" + t).encode()).hexdigest() for t in texts]
        missing = [i for i, k in enumerate(keys) if k not in self._mem]
        if missing:
            vecs = self._embed_batch([texts[i] for i in missing])
            for i, v in zip(missing, vecs):
                self._mem[keys[i]] = v
        return np.stack([self._mem[k] for k in keys]) if keys else np.zeros((0, 256), dtype=np.float32)


_default: Embedder | None = None


def default_embedder() -> Embedder:
    global _default
    if _default is None:
        _default = Embedder()
    return _default
