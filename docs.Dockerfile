# Usar una imagen de Python ligera
FROM python:3.11-slim

# Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# Instalar las dependencias de MkDocs
# Usamos mkdocstrings[python] que incluye griffe y otros requisitos
RUN pip install mkdocs-material "mkdocstrings[python]"

# Copiar los archivos de configuración y la fuente de la documentación
COPY mkdocs.yml .
COPY docs ./docs
# Copiar el código fuente de la aplicación para que mkdocstrings pueda leer los docstrings
COPY apps/agent-host/src ./apps/agent-host/src

# Exponer el puerto en el que servirá MkDocs
EXPOSE 8001

# Comando para iniciar el servidor de MkDocs
# --dev-addr 0.0.0.0:8001 permite el acceso desde fuera del contenedor
CMD ["mkdocs", "serve", "--dev-addr", "0.0.0.0:8001"]
