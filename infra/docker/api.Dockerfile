# FastAPI backend; also serves the built web app so a single container can be deployed.
FROM node:22-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web ./
RUN npx vite build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir uv && uv pip install --system -r pyproject.toml
COPY agent agent
COPY rag rag
COPY mcp_servers mcp_servers
COPY gigsim gigsim
COPY apps/__init__.py apps/__init__.py
COPY apps/api apps/api
COPY worker worker
COPY evals evals
COPY data data
COPY --from=web /web/dist apps/web/dist
RUN python -c "from rag.index.embed import _ensure_wordllama_tokenizer; _ensure_wordllama_tokenizer()"
EXPOSE 8000
HEALTHCHECK CMD curl -fs localhost:8000/api/health || exit 1
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
