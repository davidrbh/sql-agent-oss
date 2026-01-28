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
    BASE_DIR = Path("/app")
    CONFIG_DIR = DOCKER_CONFIG_PATH
else:
    try:
        # Intento de resolución para entorno local
        BASE_DIR = Path(__file__).resolve().parents[5]
    except IndexError:
        BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
    CONFIG_DIR = BASE_DIR / "config"

def load_business_context() -> str:
    """
    Carga el contexto de negocio desde el archivo YAML.
    """
    path = CONFIG_DIR / "business_context.yaml"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"No se encontró el archivo de contexto en: {path}")
        return "Sin contexto definido."

def load_data_dictionary() -> str:
    """
    Carga el diccionario de datos (esquemas de tablas) para inyectarlo en el prompt.
    Esto evita que el LLM tenga que ejecutar DESCRIBE constantemente.
    """
    path = BASE_DIR / "data" / "dictionary.yaml"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            # Simplificamos el diccionario para no saturar el contexto
            summary = []
            for table in data.get("tables", []):
                cols = [c["name"] for c in table.get("columns", [])]
                summary.append(f"- Tabla: {table['name']}\n  Columnas: {', '.join(cols)}")
            return "\n".join(summary)
    except Exception as e:
        logger.warning(f"No se pudo cargar el diccionario de datos: {e}")
        return "Diccionario no disponible."

def load_agent_prompts() -> dict:
    """
    Carga el catálogo de prompts desde config/prompts.yaml.
    """
    path = CONFIG_DIR / "prompts.yaml"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"No se pudo cargar prompts.yaml: {e}")
        return {}

def get_sql_system_prompt(channel: str = "web") -> str:
    """
    Construye el prompt de sistema extrayendo la habilidad 'sql_analysis' 
    y aplicando reglas específicas de canal.
    """
    catalog = load_agent_prompts()
    
    # 1. Identidad y Estilo Base
    persona = catalog.get("persona", "Eres un asistente virtual.")
    
    # 2. Configuración de Canal (UI/UX)
    channel_config = catalog.get("channels", {}).get(channel, {})
    style_formatting = channel_config.get("formatting", 
                       catalog.get("response_style", {}).get("formatting", ""))
    
    # 3. Habilidad SQL
    sql_skill = catalog.get("skills", {}).get("sql_analysis", {})
    sql_inst = sql_skill.get("instructions", "")
    sql_safety = sql_skill.get("safety_rules", "")
    sql_errors = sql_skill.get("error_handling", "")
    
    # 3b. Ejemplos de Entrenamiento (Few-Shot)
    examples_list = sql_skill.get("examples", [])
    examples_str = ""
    for ex in examples_list:
        examples_str += f"Pregunta: {ex['question']}\nSQL: {ex['sql']}\n\n"

    # 4. Inyección de Esquema (Schema Injection)
    schema_context = load_data_dictionary()
    
    # 5. Contexto de Negocio
    context = load_business_context()
    
    return f"""{persona}

--- MODO DE RESPUESTA ({channel.upper()}) ---
{style_formatting}

--- HABILIDAD: SQL ---
{sql_inst}

EJEMPLOS DE CONSULTAS EXITOSAS:
{examples_str}

MAPA DE TABLAS Y COLUMNAS (ESQUEMA):
{schema_context}

⚠️ REGLAS DE SEGURIDAD:
{sql_safety}

🎨 MANEJO DE ERRORES:
{sql_errors}

📘 CONTEXTO DE NEGOCIO Y DICCIONARIO DE DATOS:
```yaml
{context}
```
"""
