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

    # 6. Habilidad Lysto (Notificaciones)
    lysto_skill = catalog.get("skills", {}).get("lysto_campaigns", {})
    lysto_section = ""
    if lysto_skill:
        parts = []

        # Instructions
        inst = lysto_skill.get("instructions", "")
        if inst:
            parts.append(inst.strip())

        # Workflow
        wf = lysto_skill.get("workflow", {})
        if wf:
            wf_lines = [f"## {wf.get('title', 'FLUJO OBLIGATORIO')}"]
            for s in wf.get("steps", []):
                marker = "✅" if s.get("required") else "▪️"
                wf_lines.append(f"PASO {s['step']} → {s['action']} {marker}")
            warning = wf.get("warning", "")
            if warning:
                wf_lines.append(f"\n⚠️ {warning}")
            parts.append("\n".join(wf_lines))

        # Channels
        ch = lysto_skill.get("channels", {})
        if ch:
            ch_lines = ["## CANALES DISPONIBLES"]
            if ch.get("description"):
                ch_lines.append(ch["description"])
            ch_lines.append("| Canal | Descripción |")
            ch_lines.append("|-------|-------------|")
            for c in ch.get("available", []):
                ch_lines.append(f"| {c['id']} | {c['description']} |")
            parts.append("\n".join(ch_lines))

        # Segmentation Fields
        sf = lysto_skill.get("segmentation_fields", {})
        if sf:
            sf_lines = ["## CAMPOS DE SEGMENTACIÓN"]
            fmt = sf.get("format", "")
            if fmt:
                sf_lines.append(f"Formato de cada regla: {fmt}")
            sf_lines.append("\nCampos disponibles:")
            for f in sf.get("fields", []):
                sf_lines.append(f"- {f['name']} → {f.get('description', '').strip()}")
            sf_lines.append("\nOperadores:")
            for op in sf.get("operators", []):
                sf_lines.append(f"  {op['symbol']} → {op['meaning']}")
            comb = sf.get("combination", "")
            if comb:
                sf_lines.append(f"\n{comb}")
            parts.append("\n".join(sf_lines))

        # Placeholders
        ph = lysto_skill.get("placeholders", {})
        if ph:
            ph_lines = ["## PLACEHOLDERS PARA MENSAJES"]
            if ph.get("description"):
                ph_lines.append(ph["description"])
            for item in ph.get("available", []):
                ph_lines.append(f"- {item}")
            ex_msg = ph.get("example_message", "")
            if ex_msg:
                ph_lines.append(f'\nEjemplo: "{ex_msg}"')
            parts.append("\n".join(ph_lines))

        # Campaign Statuses
        cs = lysto_skill.get("campaign_statuses", [])
        if cs:
            cs_lines = ["## ESTADOS DE CAMPAÑA"]
            for s in cs:
                cs_lines.append(f"- {s['name']}: {s['description']}")
            parts.append("\n".join(cs_lines))

        # Behavior Rules
        br = lysto_skill.get("behavior_rules", [])
        if br:
            br_lines = ["## REGLAS DE COMPORTAMIENTO"]
            for rule in br:
                br_lines.append(f"- {rule}")
            parts.append("\n".join(br_lines))

        # Examples
        exs = lysto_skill.get("examples", [])
        if exs:
            ex_lines = ["## EJEMPLOS DE USO"]
            for ex in exs:
                ex_lines.append(f"\n**Escenario:** {ex['scenario']}")
                for step in ex.get("flow", []):
                    ex_lines.append(f"  {step}")
            parts.append("\n".join(ex_lines))

        lysto_section = "\n--- HABILIDAD: NOTIFICACIONES LYSTO ---\n" + "\n\n".join(parts)
    
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
```{lysto_section}
"""
