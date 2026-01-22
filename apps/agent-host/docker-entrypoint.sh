#!/bin/bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 [Entrypoint] Iniciando contenedor...${NC}"

# 1. Validación de Configuración
if [ ! -f "$BUSINESS_CONTEXT_PATH" ]; then
    echo "⚠️  [Warning] No se encontró business_context.yaml"
else
    echo -e "${GREEN}✅ Configuración de negocio encontrada.${NC}"
fi

# 2. Generación de Diccionario
# USAMOS RUTA ABSOLUTA PARA EVITAR ERRORES
DICT_PATH="/app/data"
DICT_FILE="$DICT_PATH/dictionary.yaml"

if [ "$SKIP_GENERATION" = "true" ]; then
    echo -e "${BLUE}⏭️  Consumer Mode: Telegram Bot (No genera nada).${NC}"
else
    echo -e "${YELLOW}🔍 Producer Mode: Verificando diccionario en: $DICT_FILE${NC}"
    
    # --- DEBUGGING: MUESTRA QUÉ HAY EN LA CARPETA ---
    echo "📂 Contenido actual de $DICT_PATH:"
    ls -la $DICT_PATH || echo "❌ No se pudo listar la carpeta data"
    # ------------------------------------------------

    if [ -f "$DICT_FILE" ] && [ "$FORCE_REGEN_DICT" != "true" ]; then
        echo -e "${GREEN}✅ El diccionario YA EXISTE. Saltando regeneración.${NC}"
    else
        echo -e "${YELLOW}📖 El diccionario no existe (o FORCE_REGEN_DICT=true). Generando...${NC}"
        
        if [ -f "scripts/generate_dictionary.py" ]; then
            python scripts/generate_dictionary.py
            echo -e "${GREEN}✅ Generación completada.${NC}"
        else
            echo -e "${RED}❌ Error: No se encuentra scripts/generate_dictionary.py${NC}"
        fi
    fi
fi

echo -e "${GREEN}🔥 Ejecutando comando: $@${NC}"
exec "$@"