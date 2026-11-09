# One image for the three GigBid MCP servers; the compose file picks the module and port.
#   docker run gigbid-mcp python -m mcp_servers.portfolio.server --http --port 8101
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
COPY data data
RUN python -c "from rag.index.embed import _ensure_wordllama_tokenizer; _ensure_wordllama_tokenizer()"
CMD ["python", "-m", "mcp_servers.portfolio.server", "--http", "--port", "8101"]
