"""
Proveedor de herramientas basado en MCP.

Este módulo implementa la interfaz IToolProvider para descubrir, conectar y 
adaptar herramientas desde múltiples servidores MCP en el ecosistema de LangChain.
"""

import os
import logging
from typing import List
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools

from core.ports.tool_provider import IToolProvider
from infra.mcp.multi_server_client import MultiServerMCPClient

logger = logging.getLogger(__name__)

class MCPToolProvider(IToolProvider):
    """
    Implementación de IToolProvider mediante el Protocolo de Contexto de Modelo (MCP).
    
    Gestiona un cliente multi-servidor para agregar capacidades desde diversos sidecars.
    """

    def __init__(self, config_json: str):
        """
        Inicializa el proveedor con las configuraciones de los servidores.

        Args:
            config_json: Cadena JSON con los perfiles de conexión MCP.
        """
        self.client = MultiServerMCPClient(config_json)
        self._tools_cache: List[BaseTool] = []

    async def get_tools(self) -> List[BaseTool]:
        """
        Descubre y adapta herramientas de todos los servidores MCP activos.
        Implementa cache para evitar re-descubrimiento en cada llamada.

        Returns:
            List[BaseTool]: Colección de herramientas compatibles con LangChain.
        """
        if self._tools_cache:
            return self._tools_cache

        await self.client.connect()
        
        all_tools = []
        sessions = self.client.get_sessions()
        
        for name, session in sessions.items():
            try:
                server_tools = await load_mcp_tools(session)
                all_tools.extend(server_tools)
                logger.info(f"Herramientas cargadas exitosamente del servidor MCP '{name}'.")
            except Exception as e:
                logger.warning(f"Error cargando herramientas del servidor MCP '{name}': {e}")
        
        self._tools_cache = all_tools
        return all_tools

    async def close(self):
        """
        Finaliza todas las conexiones MCP activas.
        """
        await self.client.close()
