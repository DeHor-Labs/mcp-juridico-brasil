# Imagem Docker do mcp-juridico-brasil
# Multi-stage para imagem final enxuta com uv.
#
# Build:
#   docker build -t mcp-juridico-brasil:0.1.0 .
#
# Run (servidor MCP stdio):
#   docker run --rm -i mcp-juridico-brasil:0.1.0
#
# Run (MCP HTTP transport):
#   docker run --rm -p 8000:8000 mcp-juridico-brasil:0.1.0 mcp-juridico-brasil --transport http
#
# Variáveis de ambiente úteis:
#   DATAJUD_API_KEY=sua_chave
#   MCP_JURIDICO_HTTP_TIMEOUT=30
#   MCP_JURIDICO_CACHE_TTL=300
#   MCP_JURIDICO_RATE_LIMIT=10
#   HOST=0.0.0.0 PORT=8000

# ---- Build stage ----
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

RUN pip install --no-cache-dir hatchling build && \
    python -m build --wheel

# ---- Runtime stage ----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0

WORKDIR /app

COPY --from=builder /build/dist/*.whl ./

RUN pip install --no-cache-dir *.whl && \
    rm -f *.whl && \
    groupadd -r app && useradd -r -g app -d /app -s /usr/sbin/nologin app && \
    chown -R app:app /app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import mcp_juridico_brasil; print('ok')" || exit 1

# Comando padrão: servidor MCP via stdio (uso por clientes MCP nativos).
CMD ["mcp-juridico-brasil"]
