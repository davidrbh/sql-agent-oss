# Etapa 1: Builder
FROM python:3.11-slim AS builder

# Evitar archivos .pyc y buffer de stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias del sistema necesarias para compilar paquetes (ej. cryptography)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    pkg-config \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Instalar Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"

# Copiar archivos de dependencia
COPY pyproject.toml poetry.lock ./

# Exportar a requirements.txt para una instalación limpia con pip
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes

# Etapa 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements desde builder
COPY --from=builder /app/requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del proyecto
COPY . .

# Exponer el puerto de Chainlit
EXPOSE 8000

# Comando de arranque
CMD ["chainlit", "run", "app.py", "--host", "0.0.0.0", "--port", "8000"]
