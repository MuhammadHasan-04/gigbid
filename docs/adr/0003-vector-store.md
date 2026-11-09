# ADR 0003: In-process numpy vectors + rank_bm25, with pgvector as the documented swap
**Context:** each portfolio has a few hundred chunks, and the deployment target is a free single container.
**Decision:** embeddings (open WordLlama weights shipped in the pip wheel, or Ollama nomic-embed / bge-m3) are held in an in-process matrix, and BM25 uses `rank_bm25`. The compose file runs Postgres with pgvector for a larger tenant.
**Consequences:** p95 retrieval stays around 1 ms on CPU and there is no network vector DB to operate. A rebuild is needed after uploads (cheap, lazy, per tenant version).
