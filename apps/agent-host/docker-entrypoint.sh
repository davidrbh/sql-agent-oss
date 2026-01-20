#!/bin/bash
set -e

echo "🚀 Entrypoint: Iniciando configuración del contenedor agent-host..."

# Paso 1: Verificar que el contexto de negocio exista.
# La ruta /app/config se mapea desde el volumen en docker-compose.yml
if [ ! -f "/app/config/business_context.yaml" ]; then
    echo "❌ Error Crítico: No se encontró el archivo 'config/business_context.yaml'."
    echo "   Por favor, asegúrate de que el archivo existe y está montado correctamente en el volumen."
    exit 1
fi

# Paso 2: Generar el diccionario usando Poetry.
# Esto asegura que el diccionario siempre esté sincronizado con el contexto de negocio al iniciar.
echo "📖 Generando diccionario desde business_context.yaml..."
poetry run python scripts/generate_dictionary.py
echo "✅ Diccionario generado con éxito."

# Paso 3: Ejecutar el comando principal pasado al contenedor (CMD en Dockerfile o command en docker-compose).
# El 'exec "$@"' ejecuta el comando que se pasó al entrypoint. En nuestro caso, será 'uvicorn...'.
echo "🚀 Iniciando el servidor Uvicorn..."
exec "$@"
