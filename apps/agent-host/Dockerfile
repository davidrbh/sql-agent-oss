# ----------------------------------------------------
# Stage 1: Builder (Poetry & Venv)
# ----------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /app

# Instalar utilidades
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN pip install poetry

# Configurar poetry para crear venv local
ENV POETRY_VIRTUALENVS_IN_PROJECT=true

# Copiar definiciones del proyecto
COPY apps/agent-host/pyproject.toml apps/agent-host/poetry.lock ./

# Instalar dependencias
RUN poetry install --no-root --no-interaction

# ----------------------------------------------------
# Stage 2: Runner
# ----------------------------------------------------
FROM python:3.11-slim AS runner

WORKDIR /app

# Crear usuario seguro
RUN addgroup --system --gid 1001 appgroup && adduser --system --uid 1001 appuser

# Copiar entorno virtual compilado
COPY --from=builder --chown=appuser:appgroup /app/.venv ./.venv

# --- COPIA DE RECURSOS DEL MONOREPO ---
# Estos folders están en la raíz del proyecto
COPY --chown=appuser:appgroup scripts ./scripts
COPY --chown=appuser:appgroup config ./config
COPY --chown=appuser:appgroup docs ./docs

# --- COPIA DEL CÓDIGO DEL AGENTE ---
COPY --chown=appuser:appgroup apps/agent-host/src ./src
COPY --chown=appuser:appgroup apps/agent-host/docker-entrypoint.sh .

# Permisos de ejecución
RUN chmod +x ./docker-entrypoint.sh

# Creamos las carpetas data y logs explícitamente y les damos permisos al usuario
RUN mkdir -p /app/data /app/logs /app/.files /app/.chainlit && \
    chown -R appuser:appgroup /app/data /app/logs /app/.files /app/.chainlit

# Variables de Entorno
ENV PATH="/app/.venv/bin:$PATH"
# Apuntamos PYTHONPATH a src para que los imports funcionen limpio
ENV PYTHONPATH=/app/src
ENV SWAGGER_JSON_PATH=/app/docs/swagger.json
ENV BUSINESS_CONTEXT_PATH=/app/config/business_context.yaml

USER appuser

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]