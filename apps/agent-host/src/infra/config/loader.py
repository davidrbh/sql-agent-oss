import os
import yaml
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
# ...

# src/agent_core/config/loader.py

# Detección inteligente del entorno (Docker vs Local)
# En Docker, la carpeta config suele estar montada en /app/config
DOCKER_CONFIG_PATH = Path("/app/config")
DOCKER_ENV_PATH = Path("/app/.env")

if DOCKER_CONFIG_PATH.exists():
    BASE_DIR = Path("/app")
    CONFIG_DIR = DOCKER_CONFIG_PATH
    # Intentamos cargar .env si existe en Docker
    if DOCKER_ENV_PATH.exists():
        load_dotenv(DOCKER_ENV_PATH)
    else:
        # Si no hay .env en /app, quizás las variables ya están en el entorno del sistema
        pass 
else:
    # Fallback para entorno local (5 niveles hacia arriba desde src/agent_core/config/loader.py)
    # Ajuste: Si estamos ejecutando desde ./apps/agent-host, la lógica relativa puede variar.
    # El previous setup usaba parents[5] para llegar a la raíz del monorepo.
    try:
        BASE_DIR = Path(__file__).resolve().parents[5]
        CONFIG_DIR = BASE_DIR / "config"
        load_dotenv(BASE_DIR / ".env")
    except IndexError:
        # Fallback extremo para desarrollo local si la estructura cambia
        logger.warning("[Config Loader] IndexError al calcular root. Usando ruta relativa fallback.")
        BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
        CONFIG_DIR = BASE_DIR / "config"
load_dotenv(BASE_DIR / ".env")

class ConfigLoader:
# ... (rest of class)
    @classmethod
    def load_settings(cls):
        """Carga config/settings.yaml"""
        if cls._settings is None:
            path = CONFIG_DIR / "settings.yaml"
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cls._settings = yaml.safe_load(f)
            except FileNotFoundError:
                # Fallback por si no existe
                cls._settings = {"app": {"debug": True}}
                logger.warning(f"Alerta: No se encontró {path}, usando valores por defecto.")
        return cls._settings

    
    @classmethod
    def get_mcp_config(cls) -> str:
        """
        Recupera la configuración del servidor MCP como una cadena JSON.
        
        Prioriza la variable de entorno MCP_SERVERS_CONFIG. Si falta, 
        recurre a un mapeo heredado de SIDECAR_URL.
        """
        config = os.getenv("MCP_SERVERS_CONFIG")
        if config:
            return config
            
        # Fallback for backward compatibility with v2.x
        sidecar_url = os.getenv("SIDECAR_URL")
        if sidecar_url:
            logger.warning("Using legacy SIDECAR_URL fallback. Consider migrating to MCP_SERVERS_CONFIG.")
            return json.dumps({
                "default": {
                    "transport": "sse",
                    "url": f"{sidecar_url}/sse"
                }
            })
            
        return "{}"

    @staticmethod
    def _find_project_root():
        # src/agent_core/config/loader.py -> ... -> root
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Subir 5 niveles para llegar a la raíz del monorepo (desde src/agent_core/config)
        # apps/agent-host/src/agent_core/config -> apps/agent-host/src/agent_core -> apps/agent-host/src -> apps/agent-host -> apps -> root
        # Ajustar según estructura real
        return os.path.abspath(os.path.join(current_dir, "../../../../../"))