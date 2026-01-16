import os
import json
from typing import List, Dict

from langchain_community.agent_toolkits.openapi.toolkit import RequestsToolkit
from langchain_community.utilities.requests import RequestsWrapper
from langchain_community.tools.json.tool import JsonSpec
from agent_core.llm.factory import LLMFactory
from dotenv import load_dotenv

load_dotenv()

def _get_swagger_path():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "../../../"))
    return os.path.join(project_root, "docs", "swagger.json")

def load_swagger_summary() -> str:
    """Genera un resumen ligero de la API para el prompt del sistema."""
    try:
        path = _get_swagger_path()
        if not os.path.exists(path): return "No API spec found."
        
        with open(path, 'r', encoding='utf-8') as f:
            spec = json.load(f)
            
        summary = ["API ENDPOINTS DISPONIBLES:"]
        for path, methods in spec.get("paths", {}).items():
            for method, details in methods.items():
                desc = details.get("summary") or details.get("description") or "Sin descripción"
                summary.append(f"- {method.upper()} {path} : {desc[:100]}") # Truncar descripción
        
        return "\n".join(summary)
    except Exception as e:
        return f"Error leyendo spec: {e}"

def load_api_tools() -> List:
    """
    Cargador Ligero (RequestsToolkit).
    Ya no usa OpenAPIToolkit pesado. Retorna solo herramientas HTTP genéricas.
    El contexto se pasa vía SystemPrompt (load_swagger_summary).
    """
    print("🔌 [API Loader] Inicializando herramientas HTTP (Light Mode)...")
    
    # ... (Auth logic remains same) ...
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
    else:
        print("   ⚠️ ADVERTENCIA: No se definieron API_AUTH_HEADER o API_AUTH_VALUE en .env")

    try:
        # Inyección dinámica de servidor para RequestsWrapper
        with open(swagger_path, 'r', encoding='utf-8') as f:
             raw_spec = json.load(f)
             
        env_base_url = os.getenv("API_BASE_URL")
        # Si no hay env, intentamos sacar del swagger
        if not env_base_url and "servers" in raw_spec:
             env_base_url = raw_spec["servers"][0].get("url")
             
        if not env_base_url:
            print("   ⚠️ No se encontró Base URL. Las llamadas pueden fallar.")
        else:
            # FIX: LangChain RequestsToolkit NO usa el base_url del wrapper automáticamente.
            # Debemos actualizar las especificaciones del swagger al vuelo o usar rutas absolutas.
            # Alternativa simple: Inyectar la URL correcta en las herramientas de langchain es complejo.
            # Mejor opción: Actualizar la spec cargada en memoria si se usara OpenAPIToolkit,
            # pero como usamos RequestsToolkit crudo, este NO tiene concepto de "base_url" por defecto.
            # RequestsWrapper SI acepta params, pero no base_url directo en __init__.
            pass

        # Creamos la wrapper con Headers
        
        # [CRITICAL FIX] Subclaseamos para interceptar llamadas y arreglar URLs relativas
        # Esto evita el error de Pydantic al intentar monkeypatching en una instancia.
        class BaseUrlRequestsWrapper(RequestsWrapper):
            def _clean_url(self, url: str) -> str:
                clean_url = str(url).strip().strip("'").strip('"')
                target_url = clean_url
                if env_base_url and not clean_url.lower().startswith("http"):
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
        
        toolkit = RequestsToolkit(requests_wrapper=requests_wrapper, allow_dangerous_requests=True)
        all_tools = toolkit.get_tools()
        
        # [OPTIMIZACIÓN] Filtramos para dejar SOLO GET (Lectura Segura)
        final_tools = []
        for tool in all_tools:
            if tool.name == "requests_get":
                # Avisamos en la descripción que la Base URL es automática
                if env_base_url:
                    tool.description += f" (Note: Base URL '{env_base_url}' is AUTOMATICALLY prepended to relative paths. Do NOT guess domains.)"
                final_tools.append(tool)
        
        print(f"   ✅ Herramientas ligeras cargadas: {len(final_tools)} (Solo GET - Read Only).")
        return final_tools

    except Exception as e:
        print(f"   ❌ Error cargando herramientas API: {e}")
        return []


if __name__ == "__main__":
    load_api_tools()