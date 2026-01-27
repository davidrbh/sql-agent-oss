# ----------------------------------------------------
# Stage 1: Builder
# ----------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN pip install poetry

ENV POETRY_VIRTUALENVS_IN_PROJECT=true

COPY services/mcp-api-sidecar/pyproject.toml ./
# Generar lock si no existe
RUN poetry lock
RUN poetry install --no-root --no-interaction

# ----------------------------------------------------
# Stage 2: Runner
# ----------------------------------------------------
FROM python:3.11-slim AS runner

WORKDIR /app

RUN addgroup --system --gid 1001 appgroup && adduser --system --uid 1001 appuser

COPY --from=builder --chown=appuser:appgroup /app/.venv ./.venv
COPY --chown=appuser:appgroup services/mcp-api-sidecar/src ./src
COPY --chown=appuser:appgroup docs/reference/api/swagger.json ./docs/swagger.json

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/src
ENV SWAGGER_JSON_PATH=/app/docs/swagger.json

USER appuser

EXPOSE 3003

# FastMCP sse transport runs on a default port or we can specify it.
# FastMCP uses starlette/uvicorn under the hood for SSE.
CMD ["python", "src/main.py"]
