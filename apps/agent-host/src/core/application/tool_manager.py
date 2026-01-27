"""
Gestor compuesto de herramientas.

Este módulo implementa un proveedor de herramientas que agrega capacidades
desde múltiples fuentes, incluyendo servidores MCP externos y cargadores
locales heredados.
"""

from typing import List
from langchain_core.tools import BaseTool

from core.ports.tool_provider import IToolProvider
from infra.mcp.tool_provider import MCPToolProvider
from infra.legacy.api_loader import load_api_tools

class CompositeToolProvider(IToolProvider):
    """
    Orquesta el descubrimiento de herramientas de múltiples fuentes (MCP y Local).
    
    Este proveedor agrega herramientas de sidecars MCP externos y cargadores locales 
    heredados, proporcionando un único punto de entrada para las capacidades del agente.
    """

    def __init__(self, mcp_provider: MCPToolProvider):
        """
        Inicializa el proveedor compuesto.

        Args:
            mcp_provider: El proveedor de herramientas basado en MCP principal.
        """
        self.mcp_provider = mcp_provider
        self._tools_cache: List[BaseTool] = []

    async def get_tools(self) -> List[BaseTool]:
        """
        Agrega herramientas de todas las fuentes configuradas.

        Returns:
            List[BaseTool]: Lista combinada de herramientas MCP y locales.
        """
        mcp_tools = await self.mcp_provider.get_tools()
        local_api_tools = load_api_tools()
        feature_tools = [] 
        
        self._tools_cache = mcp_tools + local_api_tools + feature_tools
        return self._tools_cache

    async def close(self):
        """
        Cierra todos los proveedores subyacentes.
        """
        await self.mcp_provider.close()
