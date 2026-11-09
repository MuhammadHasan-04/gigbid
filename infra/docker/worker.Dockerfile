# Arq worker: scheduled scouting, bid runs, approval resumes, marketplace sync.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir uv && uv pip install --system -r pyproject.toml
COPY agent agent
COPY rag rag
COPY mcp_servers mcp_servers
COPY gigsim gigsim
COPY apps/__init__.py apps/__init__.py
COPY apps/api apps/api
COPY worker worker
COPY data data
RUN python -c "from rag.index.embed import _ensure_wordllama_tokenizer; _ensure_wordllama_tokenizer()"
CMD ["arq", "worker.main.WorkerSettings"]
