import os
import json
from typing import List

from langchain_community.agent_toolkits.openapi.toolkit import OpenAPIToolkit
from langchain_community.utilities.requests import RequestsWrapper
from langchain_community.tools.json.tool import JsonSpec
from sql_agent.llm.factory import LLMFactory
from dotenv import load_dotenv

load_dotenv()

def load_api_tools() -> List:
    """
    Cargador Universal de APIs.
    La autenticación y la URL base se definen 100% en variables de entorno,
    haciendo este código reutilizable para cualquier API (Swagger/OpenAPI).
    """
    print("🔌 [API Loader] Inicializando herramientas de API (Modo Dinámico)...")

    # 1. Ubicación del archivo
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "../../../"))
    swagger_path = os.path.join(project_root, "docs", "swagger.json")

    if not os.path.exists(swagger_path):
        print(f"   ❌ Error: No se encontró swagger.json en: {swagger_path}")
        return []

    # 2. Configurar Autenticación Dinámica
    # El código no asume nada. Lee el nombre del header y su valor del entorno.
    auth_header = os.getenv("API_AUTH_HEADER") # Ej: "x-api-key" o "Authorization"
    auth_value = os.getenv("API_AUTH_VALUE")   # Ej: "12345" o "Bearer 12345"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    if auth_header and auth_value:
        print(f"   🔑 Inyectando credenciales dinámicas en header: '{auth_header}'")
        headers[auth_header] = auth_value
    else:
        print("   ⚠️ ADVERTENCIA: No se definieron API_AUTH_HEADER o API_AUTH_VALUE en .env")

    # 3. Leer y Parchear la Especificación
    try:
        with open(swagger_path, 'r', encoding='utf-8') as f:
            raw_spec = json.load(f)
            
        # Inyección dinámica de servidor
        env_base_url = os.getenv("API_BASE_URL")
        
        if env_base_url:
            print(f"   🎯 Servidor Base configurado: {env_base_url}")
            raw_spec["servers"] = [{"url": env_base_url}]
        
        spec = JsonSpec(dict_=raw_spec, max_value_length=4000)
        
        requests_wrapper = RequestsWrapper(headers=headers)
        llm = LLMFactory.create(temperature=0)

        # 4. Crear Toolkit
        toolkit = OpenAPIToolkit.from_llm(
            llm=llm,
            json_spec=spec,
            requests_wrapper=requests_wrapper,
            allow_dangerous_requests=True
        )
        
        tools = toolkit.get_tools()
        return tools

    except Exception as e:
        print(f"   ❌ Error cargando herramientas API: {e}")
        return []

if __name__ == "__main__":
    load_api_tools()