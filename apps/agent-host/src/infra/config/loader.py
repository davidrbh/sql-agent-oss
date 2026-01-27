"""
Cargador de configuración global.

Este módulo se encarga de centralizar la carga de archivos de configuración YAML,
la gestión de variables de entorno mediante dotenv y la provisión de perfiles
de conexión para los servidores MCP.
"""

import os
import yaml
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# --- Lógica de detección de entorno y rutas ---
DOCKER_CONFIG_PATH = Path("/app/config")
DOCKER_ENV_PATH = Path("/app/.env")

if DOCKER_CONFIG_PATH.exists():
    # Entorno Docker
    BASE_DIR = Path("/app")
    CONFIG_DIR = DOCKER_CONFIG_PATH
    if DOCKER_ENV_PATH.exists():
        load_dotenv(DOCKER_ENV_PATH)
else:
    # Entorno Local (Desarrollo)
    try:
        # Intentamos subir 5 niveles desde infra/config/loader.py hasta la raíz
        BASE_DIR = Path(__file__).resolve().parents[5]
        CONFIG_DIR = BASE_DIR / "config"
        load_dotenv(BASE_DIR / ".env")
    except IndexError:
        logger.warning("No se pudo determinar la raíz del proyecto. Usando rutas relativas.")
        BASE_DIR = Path(".")
        CONFIG_DIR = BASE_DIR / "config"

# Carga final del entorno desde la raíz detectada
load_dotenv(BASE_DIR / ".env")


class ConfigLoader:
    """
    Singleton encargado de cargar y cachear la configuración del sistema.
    """
    _settings = None

    @classmethod
    def load_settings(cls) -> dict:
        """
        Carga el archivo config/settings.yaml.

        Returns:
            dict: Diccionario con la configuración técnica del sistema.
        """
        if cls._settings is None:
            path = CONFIG_DIR / "settings.yaml"
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cls._settings = yaml.safe_load(f)
            except FileNotFoundError:
                cls._settings = {"app": {"debug": True}}
                logger.warning(f"No se encontró el archivo {path}, usando valores por defecto.")
        return cls._settings

    @classmethod
    def get_mcp_config(cls) -> str:
        """
        Recupera la configuración de los servidores MCP como una cadena JSON.

        Prioriza la variable de entorno MCP_SERVERS_CONFIG. Si no existe, genera
        una configuración compatible basada en la variable SIDECAR_URL heredada.

        Returns:
            str: Cadena JSON con la definición de los servidores MCP.
        """
        config = os.getenv("MCP_SERVERS_CONFIG")
        if config:
            return config
            
        # Compatibilidad con versiones anteriores (v2.x)
        sidecar_url = os.getenv("SIDECAR_URL")
        if sidecar_url:
            logger.info("Migrando dinámicamente SIDECAR_URL a MCP_SERVERS_CONFIG.")
            return json.dumps({
                "default": {
                    "transport": "sse",
                    "url": f"{sidecar_url}/sse"
                }
            })
            
        return "{}"

    @staticmethod
    def _find_project_root() -> str:
        """
        Resuelve la ruta absoluta de la raíz del monorepo.

        Returns:
            str: Ruta absoluta a la raíz del proyecto.
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Subir 5 niveles: infra/config/loader.py -> infra -> src -> agent-host -> apps -> root
        return os.path.abspath(os.path.join(current_dir, "../../../../../"))
