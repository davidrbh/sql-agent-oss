"""
Servidor MCP para integraci0n de APIs externas.

Este servicio expone herramientas para interactuar con APIs REST externas
basadas en una especificaci0n Swagger/OpenAPI, permitiendo al agente
realizar consultas operacionales en tiempo real mediante el protocolo MCP.
"""

import os
import json
import logging
from typing import List, Optional

from mcp.server.fastmcp import FastMCP
from langchain_community.utilities.requests import RequestsWrapper

# Configuraci0n de logging profesional
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("mcp-api-sidecar")

# Inicializaci0n de FastMCP como servidor de herramientas
mcp = FastMCP("API Sidecar", json_response=True)

# Variables de entorno para configuraci0n de la API objetivo
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:3000")
API_AUTH_HEADER = os.getenv("API_AUTH_HEADER")
API_AUTH_VALUE = os.getenv("API_AUTH_VALUE")
SWAGGER_PATH = os.getenv("SWAGGER_JSON_PATH", "/app/docs/swagger.json")

def get_requests_wrapper() -> RequestsWrapper:
    """
    Configura y devuelve un wrapper de peticiones HTTP con auth.
    """
    headers = {"Content-Type": "application/json"}
    if API_AUTH_HEADER and API_AUTH_VALUE:
        headers[API_AUTH_HEADER] = API_AUTH_VALUE
    
    class BaseUrlRequestsWrapper(RequestsWrapper):
        def _clean_url(self, url: str) -> str:
            clean_url = str(url).strip().strip("'").strip('"')
            if clean_url.lower().startswith("http"):
                return clean_url
            base = API_BASE_URL.rstrip("/")
            path = clean_url.lstrip("/")
            return f"{base}/{path}"

        def get(self, url: str, **kwargs):
            return super().get(self._clean_url(url), **kwargs)

        async def aget(self, url: str, **kwargs):
            return await super().aget(self._clean_url(url), **kwargs)

    return BaseUrlRequestsWrapper(headers=headers)

# Instancia global para ser utilizada por las herramientas del servidor
requests_wrapper = get_requests_wrapper()

@mcp.tool()
async def api_get(path: str, params: Optional[dict] = None) -> str:
    """
    Realiza una petici0n GET a la API externa vinculada.
    
    Args:
        path: Ruta relativa del endpoint (ej: '/admin/users').
        params: Diccionario opcional de par0metros de consulta.
    """
    logger.info(f"Ejecutando petici0n GET en ruta: {path}")
    try:
        response = await requests_wrapper.aget(path, params=params)
        return response
    except Exception as e:
        logger.error(f"Error cr0tico en petici0n API: {str(e)}")
        return f"Error de comunicaci0n con la API: {str(e)}"

@mcp.tool()
def list_api_endpoints() -> str:
    """
    Provee un resumen de los endpoints disponibles en la API.
    """
    if not os.path.exists(SWAGGER_PATH):
        logger.warning(f"No se encontr0 el archivo Swagger en: {SWAGGER_PATH}")
        return "Error: Documentaci0n de API (Swagger) no encontrada en el sistema."
    
    try:
        with open(SWAGGER_PATH, 'r', encoding='utf-8') as f:
            spec = json.load(f)
            
        summary = ["ENDPOINTS DISPONIBLES EN EL SISTEMA:"]
        for path, methods in spec.get("paths", {}).items():
            for method, details in methods.items():
                desc = details.get("summary") or details.get("description") or "Sin descripci0n"
                summary.append(f"- {method.upper()} {path} : {desc[:100]}") 
        
        return "\n".join(summary)
    except Exception as e:
        logger.error(f"Fallo al leer la especificaci0n Swagger: {str(e)}")
        return f"Error interno al procesar la documentaci0n de la API: {str(e)}"

if __name__ == "__main__":
    import uvicorn
    # Arranca el servidor MCP usando el transporte SSE expuesto como una app Starlette
    # Se expone en todas las interfaces para ser accesible desde el contenedor del agente
    uvicorn.run(mcp.sse_app(), host="0.0.0.0", port=3003)
