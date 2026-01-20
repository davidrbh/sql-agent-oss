import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

# src/agent_core/config/loader.py -> ... -> root (5 niveles de padres)
BASE_DIR = Path(__file__).resolve().parents[5]
CONFIG_DIR = BASE_DIR / "config"
load_dotenv(BASE_DIR / ".env")

class ConfigLoader:
    """
    Singleton encargado de cargar la configuración una sola vez.
    """
    _settings = None
    _business_context = None

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
                print(f"⚠️ Alerta: No se encontró {path}, usando valores por defecto.")
        return cls._settings

    
    @staticmethod
    def _find_project_root():
        # src/agent_core/config/loader.py -> ... -> root
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Subir 5 niveles para llegar a la raíz del monorepo (desde src/agent_core/config)
        # apps/agent-host/src/agent_core/config -> apps/agent-host/src/agent_core -> apps/agent-host/src -> apps/agent-host -> apps -> root
        # Ajustar según estructura real
        return os.path.abspath(os.path.join(current_dir, "../../../../../"))