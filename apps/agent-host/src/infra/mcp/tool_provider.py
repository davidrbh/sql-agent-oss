import os
from typing import List
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools

from core.ports.tool_provider import IToolProvider
from infra.mcp.multi_server_client import MultiServerMCPClient

class MCPToolProvider(IToolProvider):
    """
    Implementación de IToolProvider usando el Protocolo de Contexto de Modelo (MCP).
    
    Esta clase gestiona un MultiServerMCPClient para descubrir y adaptar herramientas 
    de varios sidecars MCP en herramientas compatibles con LangChain.
    """

    def __init__(self, config_json: str):
        """
        Inicializa el proveedor con configuraciones de servidor.

        Args:
            config_json: Cadena JSON con los perfiles de conexión para servidores MCP.
        """
        self.client = MultiServerMCPClient(config_json)
        self._tools_cache: List[BaseTool] = []

    async def get_tools(self) -> List[BaseTool]:
        """
        Descubre y carga herramientas de todos los servidores MCP configurados.
        
        Este método asegura que las conexiones estén activas, recupera herramientas de cada 
        sesión y utiliza el adaptador de LangChain para convertirlas.

        Returns:
            List[BaseTool]: Lista agregada de herramientas de todos los servidores conectados.
        """
        # Asegurar que estamos conectados
        await self.client.connect()
        
        all_tools = []
        sessions = self.client.get_sessions()
        
        for name, session in sessions.items():
            try:
                # Usar langchain-mcp-adapters para convertir herramientas de sesión
                server_tools = await load_mcp_tools(session)
                all_tools.extend(server_tools)
            except Exception as e:
                print(f"⚠️ Error cargando herramientas del servidor MCP '{name}': {e}")
        
        self._tools_cache = all_tools
        return all_tools

    async def close(self):
        """Cierra todas las sesiones MCP activas."""
        await self.client.close()