# Single-container public deployment (Hugging Face Spaces, Docker SDK, port 7860).
# Runs GigSim + the API (with the worker inline) + the built web app. Postgres: DATABASE_URL secret
# (e.g. Neon); if absent, an embedded Postgres is started in the container (state is lost on restart).
FROM node:22-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web ./
RUN npx vite build

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends postgresql postgresql-contrib curl && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app HOME=/home/user
WORKDIR /app
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir uv && UV_NO_CACHE=1 uv pip install --system -r pyproject.toml
COPY --chown=user agent agent
COPY --chown=user rag rag
COPY --chown=user mcp_servers mcp_servers
COPY --chown=user gigsim gigsim
COPY --chown=user apps/__init__.py apps/__init__.py
COPY --chown=user apps/api apps/api
COPY --chown=user worker worker
COPY --chown=user evals evals
COPY --chown=user data data
COPY --chown=user deploy/hf-space/start.sh /app/start.sh
COPY --from=web --chown=user /web/dist apps/web/dist
RUN chmod +x /app/start.sh && mkdir -p /app/data/runtime /app/data/processed && chown -R user /app/data \
    && rm -rf /home/user/.cache && chown -R user:user /home/user
USER user
RUN python -c "from rag.index.embed import _ensure_wordllama_tokenizer; _ensure_wordllama_tokenizer()"
ENV GIGSIM_REAL_JOBS=1 MALLOC_ARENA_MAX=2 INLINE_CONCURRENCY=2 RUN_INLINE=1 MCP_TRANSPORT=inproc GIGSIM_BASE_URL=http://127.0.0.1:8081 GIGSIM_RPM=600 GIGSIM_POLICY_VERSION=2 POLICY_VERSION=2
EXPOSE 7860
CMD ["/app/start.sh"]
