import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

# Definimos la raíz del proyecto basándonos en la ubicación de este archivo
# src/sql_agent/config/loader.py -> ... -> root
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
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

    @classmethod
    def load_context(cls):
        """Carga config/business_context.yaml y lo devuelve como string YAML"""
        if cls._business_context is None:
            path = CONFIG_DIR / "business_context.yaml"
            try:
                with open(path, "r", encoding="utf-8") as f:
                    # Leemos el archivo crudo para pasarlo tal cual al LLM,
                    # manteniendo los comentarios y estructura visual que ayudan al modelo.
                    cls._business_context = f.read()
            except FileNotFoundError:
                cls._business_context = "Sin contexto definido."
                print(f"⚠️ Alerta: No se encontró {path}")
        return cls._business_context