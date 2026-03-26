"""
Cargador de la feature de análisis SQL.

Este módulo gestiona el contexto de negocio y construye los prompts del sistema
para la capacidad Text-to-SQL. Actúa como un Vertical Slice puro:
aísla las reglas de dominio SQL de la infraestructura y de otros features.

Responsabilidades:
  - Cargar config/prompts.yaml (persona, canal, skill sql_analysis).
  - Cargar config/business_context.yaml (contexto de negocio del cliente).
  - Cargar data/dictionary.yaml (esquema de tablas de la BD objetivo).
  - Componer y retornar un prompt de sistema listo para inyectar al LLM.
"""

import os
import yaml
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resolución de rutas compatible con Docker y entorno local de desarrollo.
# ---------------------------------------------------------------------------
_DOCKER_CONFIG_PATH = Path("/app/config")

if _DOCKER_CONFIG_PATH.exists():
    _BASE_DIR = Path("/app")
    _CONFIG_DIR = _DOCKER_CONFIG_PATH
else:
    try:
        # Sube desde features/sql_analysis/loader.py hasta la raíz del monorepo
        _BASE_DIR = Path(__file__).resolve().parents[5]
    except IndexError:
        _BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
    _CONFIG_DIR = _BASE_DIR / "config"


# ---------------------------------------------------------------------------
# Funciones privadas de carga de archivos
# ---------------------------------------------------------------------------

def load_business_context() -> str:
    """
    Carga el contexto de negocio desde config/business_context.yaml.

    Este archivo describe el dominio del negocio del cliente final (terminología,
    procesos, entidades clave). Se inyecta en el prompt para que el LLM
    comprenda el vocabulario del negocio al interpretar preguntas en lenguaje natural.

    Returns:
        str: Contenido YAML del contexto de negocio, o mensaje de fallback.
    """
    path = _CONFIG_DIR / "business_context.yaml"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("No se encontró business_context.yaml en: %s", path)
        return "Sin contexto de negocio definido."


def load_data_dictionary() -> str:
    """
    Carga el esquema de tablas desde data/dictionary.yaml.

    Construye un resumen compacto (tabla → columnas) para inyectarlo en el prompt
    sin saturar el contexto. Evita que el LLM tenga que ejecutar DESCRIBE
    en cada consulta, mejorando la exactitud y la velocidad de respuesta.

    Returns:
        str: Resumen legible del esquema de tablas disponibles.
    """
    path = _BASE_DIR / "data" / "dictionary.yaml"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            summary = []
            for table in data.get("tables", []):
                cols = [c["name"] for c in table.get("columns", [])]
                summary.append(f"- Tabla: {table['name']}\n  Columnas: {', '.join(cols)}")
            return "\n".join(summary)
    except Exception as e:
        logger.warning("No se pudo cargar el diccionario de datos: %s", e)
        return "Diccionario no disponible."


def load_agent_prompts() -> dict:
    """
    Carga el catálogo de prompts desde config/prompts.yaml.

    Returns:
        dict: Catálogo completo de skills, persona y configuración de canales.
    """
    path = _CONFIG_DIR / "prompts.yaml"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("No se pudo cargar prompts.yaml: %s", e)
        return {}


# ---------------------------------------------------------------------------
# API pública del módulo
# ---------------------------------------------------------------------------

def get_sql_system_prompt(channel: str = "web") -> str:
    """
    Construye el prompt de sistema para el agente especializado en análisis SQL.

    Compone el prompt combinando: identidad del agente, reglas de formato del
    canal, instrucciones de la skill SQL (con ejemplos few-shot y reglas de
    seguridad), el esquema de tablas inyectado y el contexto de negocio.

    Args:
        channel: Canal de comunicación activo ('web', 'whatsapp', 'telegram').
                 Determina las reglas de formato de la respuesta.

    Returns:
        str: Prompt de sistema listo para inyectar como SystemMessage al LLM.
    """
    catalog = load_agent_prompts()

    # 1. Identidad base del agente
    persona: str = catalog.get("persona", "Eres un asistente virtual.")

    # 2. Reglas de formato del canal seleccionado
    channel_config: dict = catalog.get("channels", {}).get(channel, {})
    style_formatting: str = channel_config.get(
        "formatting",
        catalog.get("response_style", {}).get("formatting", "")
    )

    # 3. Instrucciones y reglas de la skill SQL
    sql_skill: dict = catalog.get("skills", {}).get("sql_analysis", {})
    sql_instructions: str = sql_skill.get("instructions", "")
    sql_safety: str = sql_skill.get("safety_rules", "")
    sql_error_handling: str = sql_skill.get("error_handling", "")

    # 4. Ejemplos few-shot de consultas exitosas
    examples_list: list = sql_skill.get("examples", [])
    examples_str: str = ""
    for ex in examples_list:
        examples_str += f"Pregunta: {ex['question']}\nSQL: {ex['sql']}\n\n"

    # 5. Esquema de tablas de la base de datos objetivo
    schema_context: str = load_data_dictionary()

    # 6. Contexto de negocio del cliente final
    business_context: str = load_business_context()

    return f"""{persona}

--- MODO DE RESPUESTA ({channel.upper()}) ---
{style_formatting}

--- HABILIDAD: SQL ---
{sql_instructions}

EJEMPLOS DE CONSULTAS EXITOSAS:
{examples_str}

MAPA DE TABLAS Y COLUMNAS (ESQUEMA):
{schema_context}

⚠️ REGLAS DE SEGURIDAD:
{sql_safety}

🎨 MANEJO DE ERRORES:
{sql_error_handling}

📘 CONTEXTO DE NEGOCIO Y DICCIONARIO DE DATOS:
```yaml
{business_context}
```"""
