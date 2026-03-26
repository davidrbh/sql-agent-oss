"""
Cargador de la feature de análisis de Google Sheets.

Este módulo construye el prompt de sistema especializado para el modo de análisis
de hojas de cálculo LibrePago. Sigue el mismo patrón de Vertical Slice que
sql_analysis/loader.py: aísla las reglas de dominio de Sheets de la infraestructura,
leyendo el catálogo de prompts y el diccionario de conocimiento de dominio.

Responsabilidades:
  - Cargar config/prompts.yaml (persona, canal, skill google_sheets).
  - Cargar config/sheets_knowledge.yaml (estructura de cada spreadsheet y mapeos de IDs).
  - Componer y retornar un prompt de sistema listo para inyectar al LLM.
"""

import yaml
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resolución de rutas compatible con Docker y entorno local de desarrollo.
# Sigue el mismo mecanismo que sql_analysis/loader.py para consistencia.
# ---------------------------------------------------------------------------
_DOCKER_CONFIG_PATH = Path("/app/config")

if _DOCKER_CONFIG_PATH.exists():
    _BASE_DIR = Path("/app")
    _CONFIG_DIR = _DOCKER_CONFIG_PATH
else:
    try:
        # Sube desde features/sheets_analysis/loader.py hasta la raíz del monorepo
        _BASE_DIR = Path(__file__).resolve().parents[5]
    except IndexError:
        _BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
    _CONFIG_DIR = _BASE_DIR / "config"


# ---------------------------------------------------------------------------
# Funciones privadas de carga de archivos
# ---------------------------------------------------------------------------

def _load_agent_prompts() -> dict:
    """
    Carga el catálogo de prompts desde config/prompts.yaml.

    Returns:
        dict: Catálogo completo de skills, persona y configuración de canales.
    """
    path = _CONFIG_DIR / "prompts.yaml"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("No se encontró prompts.yaml en: %s", path)
        return {}
    except yaml.YAMLError as e:
        logger.error("Error parseando prompts.yaml: %s", e)
        return {}


def _load_sheets_knowledge() -> dict:
    """
    Carga el diccionario de dominio de Google Sheets desde sheets_knowledge.yaml.

    Returns:
        dict: Estructura completa de spreadsheets, campos y tablas de mapeo de IDs.
    """
    path = _CONFIG_DIR / "sheets_knowledge.yaml"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.warning("No se encontró sheets_knowledge.yaml en: %s", path)
        return {}
    except yaml.YAMLError as e:
        logger.error("Error parseando sheets_knowledge.yaml: %s", e)
        return {}


# ---------------------------------------------------------------------------
# Funciones privadas de construcción del prompt
# ---------------------------------------------------------------------------

def _build_spreadsheets_section(knowledge: dict) -> str:
    """
    Construye la sección del prompt que describe cada spreadsheet disponible.

    Args:
        knowledge: Diccionario cargado desde sheets_knowledge.yaml.

    Returns:
        str: Bloque de texto formateado con la estructura de cada hoja.
    """
    spreadsheets = knowledge.get("spreadsheets", {})
    if not spreadsheets:
        return "No hay hojas de cálculo configuradas."

    lines = []
    for key, sheet in spreadsheets.items():
        lines.append(f"\n### {sheet.get('title', key.upper())}")
        lines.append(f"- **Spreadsheet ID:** `{sheet.get('id', 'N/A')}`")
        lines.append(f"- **Pestaña activa:** `{sheet.get('sheet_name', 'Hoja 1')}`")
        lines.append(f"- **Descripción:** {sheet.get('description', '').strip()}")

        # Campos activos (excluir los marcados como ignore)
        active_fields = [
            f for f in sheet.get("fields", [])
            if not f.get("ignore", False)
        ]
        if active_fields:
            lines.append("- **Campos disponibles:**")
            for field in active_fields:
                desc = field.get("description", "").strip().replace("\n", " ")
                lines.append(f"  - `{field['name']}`: {desc}")

        # Etapas del pipeline (solo para Ciclos de Vida)
        stages = sheet.get("pipeline_stages", [])
        if stages:
            lines.append("- **Etapas del pipeline:**")
            for stage in stages:
                lines.append(f"  - **{stage['name']}**: {stage['meaning']}")

        # Ejemplos de consulta representativos
        examples = sheet.get("example_queries", [])
        if examples:
            lines.append("- **Ejemplos de consulta:**")
            for ex in examples:
                ex_text = ex.strip().replace("\n", " ") if isinstance(ex, str) else str(ex)
                lines.append(f"  - \"{ex_text}\"")

    return "\n".join(lines)


def _build_id_mappings_section(knowledge: dict) -> str:
    """
    Construye la sección del prompt con las tablas de mapeo de IDs.

    Args:
        knowledge: Diccionario cargado desde sheets_knowledge.yaml.

    Returns:
        str: Texto formateado con las tablas de canales, agentes y equipos.
    """
    mappings = knowledge.get("id_mappings", {})
    if not mappings:
        return ""

    lines = []

    # Canales
    channels = mappings.get("channels", {})
    if channels.get("entries"):
        lines.append("\n**Canales (ID → Nombre):**")
        lines.append("| ID(s) | Canal |")
        lines.append("|-------|-------|")
        for entry in channels["entries"]:
            ids_str = ", ".join(entry.get("ids", []))
            lines.append(f"| {ids_str} | {entry['name']} |")

    # Agentes
    agents = mappings.get("agents", {})
    if agents.get("entries"):
        lines.append("\n**Agentes (ID → Nombre → Tipo):**")
        lines.append("| ID | Nombre | Tipo |")
        lines.append("|----|--------|------|")
        for entry in agents["entries"]:
            lines.append(
                f"| {entry['id']} | {entry['name']} | {entry['type']} |"
            )

    # Equipos
    teams = mappings.get("teams", {})
    if teams.get("entries"):
        lines.append("\n**Equipos (ID → Nombre):**")
        lines.append("| ID | Nombre | Descripción |")
        lines.append("|----|--------|-------------|")
        for entry in teams["entries"]:
            lines.append(
                f"| {entry['id']} | {entry['name']} | {entry.get('description', '')} |"
            )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# API pública del módulo
# ---------------------------------------------------------------------------

def get_sheets_system_prompt(channel: str = "web") -> str:
    """
    Construye el prompt de sistema para el agente especializado en Google Sheets.

    Lee config/prompts.yaml y config/sheets_knowledge.yaml para componer
    un prompt completo que incluye: identidad, reglas de canal, instrucciones
    de la skill, estructura de cada spreadsheet y tablas de mapeo de IDs.

    Args:
        channel: Canal de comunicación activo ('web', 'whatsapp', 'telegram').
                 Determina las reglas de formato de la respuesta.

    Returns:
        str: Prompt de sistema listo para inyectar como SystemMessage al LLM.
    """
    catalog = _load_agent_prompts()
    knowledge = _load_sheets_knowledge()

    # 1. Identidad base del agente
    persona: str = catalog.get("persona", "Eres un asistente de análisis de datos.")

    # 2. Reglas de formato del canal seleccionado
    channel_config: dict = catalog.get("channels", {}).get(channel, {})
    style_formatting: str = channel_config.get(
        "formatting",
        catalog.get("response_style", {}).get("formatting", "")
    )

    # 3. Instrucciones y reglas de comportamiento de la skill google_sheets
    sheets_skill: dict = catalog.get("skills", {}).get("google_sheets", {})
    skill_instructions: str = sheets_skill.get("instructions", "")

    behavior_rules: list = sheets_skill.get("behavior_rules", [])
    behavior_section: str = ""
    if behavior_rules:
        behavior_section = "REGLAS DE COMPORTAMIENTO:\n" + "\n".join(
            f"- {rule}" for rule in behavior_rules
        )

    # 4. Estructura detallada de los spreadsheets (del diccionario de dominio)
    spreadsheets_section: str = _build_spreadsheets_section(knowledge)

    # 5. Tablas de mapeo de IDs (canales, agentes, equipos)
    id_mappings_section: str = _build_id_mappings_section(knowledge)

    return f"""{persona}

--- MODO DE RESPUESTA ({channel.upper()}) ---
{style_formatting}

--- HABILIDAD: GOOGLE SHEETS ---
{skill_instructions}

{behavior_section}

--- HOJAS DE CÁLCULO DISPONIBLES ---
{spreadsheets_section}

--- TABLAS DE MAPEO DE IDs ---
IMPORTANTE: Usa estas tablas para traducir IDs numéricos a nombres legibles
antes de presentar cualquier resultado al usuario.
{id_mappings_section}
"""
