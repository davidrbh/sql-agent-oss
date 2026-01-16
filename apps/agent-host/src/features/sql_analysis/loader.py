import os
import yaml
from pathlib import Path
from langchain_core.messages import SystemMessage
from infra.mcp.loader import get_agent_tools as get_mcp_tools # Reusing existing generic MCP loader if possible
# Assuming infra/mcp/loader.py is generic enough. Let's verify that first.

# We need to calculate paths relative to this feature
# apps/agent-host/src/features/sql_analysis/loader.py

# Detección inteligente del entorno (Docker vs Local)
# En Docker, WORKDIR es /app, así que config suele estar en /app/config
DOCKER_CONFIG_PATH = Path("/app/config")

if DOCKER_CONFIG_PATH.exists():
    CONFIG_DIR = DOCKER_CONFIG_PATH
else:
    # Fallback para entorno local (Monorepo)
    # Subimos niveles hasta encontrar la carpeta config en la raíz del proyecto
    # src/features/sql_analysis/loader.py -> ... -> sql-agent-oss/config
    BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
    CONFIG_DIR = BASE_DIR / "config"

SYSTEM_PROMPT_TEMPLATE = """Eres un experto Agente SQL.

⚠️ REGLAS CRÍTICAS DE SEGURIDAD ⚠️
1. PROHIBIDO ejecutar `SELECT *` en la tabla `users`. Contiene columnas de imágenes Base64 (doc_photo, selfie_photo) que rompen la conexión.
2. ANTES de consultar `users`, SIEMPRE ejecuta `DESCRIBE users` para ver las columnas disponibles.
3. Selecciona SIEMPRE columnas específicas (ej. `SELECT id, name, email FROM users...`).
4. Para otras tablas, inspecciona primero el esquema igualmente.

🎨 ESTILO DE RESPUESTA:
- Sé amable y conciso.
- EVITA el uso excesivo de saltos de línea (\\n).
- Cuando listes datos simples (como nombres), úsalos separados por comas.
"""

def load_business_context() -> str:
    """Loads business context from YAML"""
    path = CONFIG_DIR / "business_context.yaml"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"⚠️ Alerta: No se encontró {path}")
        return "Sin contexto definido."

def get_sql_system_prompt() -> str:
    """Generates the full system prompt for SQL Analysis"""
    context = load_business_context()
    return f"""{SYSTEM_PROMPT_TEMPLATE}

📘 CONTEXTO DE NEGOCIO Y DICCIONARIO DE DATOS:
A continuación se definen las entidades, sinónimos y reglas de negocio. ÚSALO para entender qué tabla consultar según los términos del usuario.

```yaml
{context}
```
"""

async def get_sql_tools(mcp_manager):
    """Facade to get tools for this specific feature"""
    # In the future, this could filter specific tools from the MCP session if needed
    from agent_core.api.loader import load_api_tools
    
    mcp_tools = await get_mcp_tools(mcp_manager)
    api_tools = load_api_tools() # Reads config from env
    
    return mcp_tools + api_tools
