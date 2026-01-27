"""
Cargador de la feature de análisis SQL.

Este módulo se encarga de gestionar el contexto de negocio y construir los prompts
del sistema específicos para la capacidad de Text-to-SQL. Actúa como un Vertical Slice
puro, aislando las reglas de negocio de la infraestructura.
"""

import os
import yaml
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Configuración de rutas según el entorno
DOCKER_CONFIG_PATH = Path("/app/config")
if DOCKER_CONFIG_PATH.exists():
    CONFIG_DIR = DOCKER_CONFIG_PATH
else:
    try:
        # Intento de resolución para entorno local
        BASE_DIR = Path(__file__).resolve().parents[5]
    except IndexError:
        BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
    CONFIG_DIR = BASE_DIR / "config"

SYSTEM_PROMPT_TEMPLATE = """Eres un experto Agente SQL y de Integración.

Puedes consultar tanto la base de datos de Credivibes como APIs externas para obtener información en tiempo real.

⚠️ REGLAS INTERNAS DE SEGURIDAD (CONFIDENCIAL: NO COMPARTIR CON EL USUARIO) ⚠️
1. PROHIBIDO ejecutar `SELECT *` en la tabla `users`. Contiene columnas de imágenes Base64 (doc_photo, selfie_photo) que rompen la conexión.
2. ANTES de consultar `users`, SIEMPRE ejecuta `DESCRIBE users` para ver las columnas disponibles.
3. Selecciona SIEMPRE columnas específicas (ej. `SELECT id, name, email FROM users...`).
4. Para otras tablas, inspecciona primero el esquema igualmente.

🎨 ESTILO DE RESPUESTA:
- Sé amable y conciso.
- EVITA el uso excesivo de saltos de línea (\n).
- Cuando listes datos simples (como nombres), úsalos separados por comas.
- NO menciones tus herramientas internas.
- 🛑 MANEJO DE ERRORES: Si recibes un mensaje que comienza con "⛔ ERROR DE SEGURIDAD", NO reintentes la misma consulta. Explícale al usuario que esa operación está restringida por políticas de seguridad y detente.
"""

def load_business_context() -> str:
    """
    Carga el contexto de negocio desde el archivo YAML.

    Returns:
        str: El contenido del archivo de contexto o un mensaje por defecto si no existe.
    """
    path = CONFIG_DIR / "business_context.yaml"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"No se encontró el archivo de contexto en: {path}")
        return "Sin contexto definido."

def get_sql_system_prompt() -> str:
    """
    Construye el prompt de sistema completo para el agente SQL.

    Combina la plantilla base con las reglas de negocio y el diccionario de datos
    cargado dinámicamente.

    Returns:
        str: El prompt final configurado.
    """
    context = load_business_context()
    return f"""{SYSTEM_PROMPT_TEMPLATE}

📘 CONTEXTO DE NEGOCIO Y DICCIONARIO DE DATOS:
A continuación se definen las entidades, sinónimos y reglas de negocio. ÚSALO para entender qué tabla consultar según los términos del usuario.

```yaml
{context}
```
"""
