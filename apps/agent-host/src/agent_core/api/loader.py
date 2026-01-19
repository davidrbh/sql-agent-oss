import os
import json
from typing import List, Dict

from langchain_community.agent_toolkits.openapi.toolkit import RequestsToolkit
from langchain_community.utilities.requests import RequestsWrapper
from langchain_community.tools.json.tool import JsonSpec
from dotenv import load_dotenv

load_dotenv()

def _get_swagger_path():
    """
    Estrategia de resolución de ruta Híbrida para encontrar swagger.json.

    1. Prioridad: Variable de entorno SWAGGER_JSON_PATH (Ruta Absoluta - Ideal para Local/Turbo).
    2. Fallback: Cálculo relativo robusto desde la ubicación de este archivo.
    """
    # 1. Intentar cargar desde variable de entorno (Configuración robusta)
    env_path = os.getenv("SWAGGER_JSON_PATH")
    if env_path:
        if os.path.exists(env_path):
            return env_path
        else:
            print(f"⚠️ [API Loader] La ruta en SWAGGER_JSON_PATH no existe: {env_path}")

    # 2. Fallback: Cálculo relativo robusto usando pathlib
    # Sube 6 niveles desde la ubicación actual para llegar a la raíz del monorepo
    # .../src/agent_core/api/loader.py -> ... -> raíz
    try:
        from pathlib import Path
        project_root = Path(__file__).resolve().parents[5]
        return str(project_root / "docs" / "swagger.json")
    except IndexError:
        print("❌ [API Loader] No se pudo calcular la ruta raíz del proyecto.")
        # Fallback a una ruta por defecto si todo falla
        return "docs/swagger.json"

def load_swagger_summary() -> str:
    """Genera un resumen ligero de la API para el prompt del sistema."""
    try:
        path = _get_swagger_path()
        if not os.path.exists(path): 
            print(f"❌ [API Loader] Swagger no encontrado en: {path}")
            return "No API spec found."
        
        with open(path, 'r', encoding='utf-8') as f:
            spec = json.load(f)
            
        summary = ["API ENDPOINTS DISPONIBLES:"]
        for path, methods in spec.get("paths", {}).items():
            for method, details in methods.items():
                desc = details.get("summary") or details.get("description") or "Sin descripción"
                summary.append(f"- {method.upper()} {path} : {desc[:100]}") 
        
        return "\n".join(summary)
    except Exception as e:
        return f"Error leyendo spec: {e}"

def load_api_tools() -> List:
    """
    Cargador Ligero (RequestsToolkit).
    """
    print("🔌 [API Loader] Inicializando herramientas HTTP (Light Mode)...")
    
    swagger_path = _get_swagger_path()
    
    # 2. Configurar Autenticación Dinámica
    auth_header = os.getenv("API_AUTH_HEADER")
    auth_value = os.getenv("API_AUTH_VALUE")
    
    headers = {
        "Content-Type": "application/json"
    }
    
    if auth_header and auth_value:
        print(f"   🔑 Inyectando credenciales dinámicas en header: '{auth_header}'")
        headers[auth_header] = auth_value
    
    try:
        # Definir Base URL: Prioridad ENV > Fallback Localhost
        # Usamos SIDECAR_URL o API_BASE_URL, o un default
        env_base_url = os.getenv("API_BASE_URL") or os.getenv("SIDECAR_URL")
        
        if not env_base_url:
            # Fallback inteligente para desarrollo local
            env_base_url = "http://localhost:3000"
            print("   ⚠️ No se encontró API_BASE_URL. Usando default: http://localhost:3000")
        
        # Limpiamos la URL (quitamos /sse si viene de SIDECAR_URL)
        if "/sse" in env_base_url:
            env_base_url = env_base_url.replace("/sse", "")

        # Wrapper Personalizado para Inyección de URL Base
        class BaseUrlRequestsWrapper(RequestsWrapper):
            def _clean_url(self, url: str) -> str:
                clean_url = str(url).strip().strip("'").strip('"')
                
                # Si la URL ya es absoluta (http...), la respetamos
                if clean_url.lower().startswith("http"):
                    return clean_url
                
                # Si es relativa, le pegamos el base_url
                base = env_base_url.rstrip("/")
                path = clean_url.lstrip("/")
                target_url = f"{base}/{path}"
                print(f"   🔄 [URL Rewrite] '{clean_url}' -> '{target_url}'")
                return target_url

            def get(self, url: str, **kwargs):
                target_url = self._clean_url(url)
                return super().get(target_url, **kwargs)

            async def aget(self, url: str, **kwargs):
                target_url = self._clean_url(url)
                return await super().aget(target_url, **kwargs)

        requests_wrapper = BaseUrlRequestsWrapper(headers=headers)
        
        # RequestsToolkit crudo (sin OpenAPISpec pesado)
        toolkit = RequestsToolkit(requests_wrapper=requests_wrapper, allow_dangerous_requests=True)
        all_tools = toolkit.get_tools()
        
        final_tools = []
        for tool in all_tools:
            # Solo permitimos GET para seguridad en esta fase
            if tool.name == "requests_get":
                if env_base_url:
                    tool.description += f" (Note: Base URL '{env_base_url}' is AUTOMATICALLY prepended. Use relative paths like '/users'.)"
                final_tools.append(tool)
        
        print(f"   ✅ Herramientas ligeras cargadas: {len(final_tools)} (Solo GET - Read Only).")
        return final_tools

    except Exception as e:
        print(f"   ❌ Error cargando herramientas API: {e}")
        return []

if __name__ == "__main__":
    load_api_tools()