"""
Gestor compuesto de herramientas.

Este módulo implementa un proveedor de herramientas que agrega capacidades
desde múltiples fuentes, consolidando actualmente todas las herramientas
bajo el protocolo MCP.
"""

from typing import List
from langchain_core.tools import BaseTool

from core.ports.tool_provider import IToolProvider
from infra.mcp.tool_provider import MCPToolProvider

class CompositeToolProvider(IToolProvider):
    """
    Orquesta el descubrimiento de herramientas mediante el protocolo MCP.
    
    Este proveedor actúa como el punto central para obtener capacidades
    del agente, las cuales se descubren dinámicamente desde los sidecars
    MCP configurados.
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
        Agrega herramientas de todas las fuentes MCP configuradas.
        Implementa cache para optimizar el rendimiento.

        Returns:
            List[BaseTool]: Lista combinada de herramientas descubiertas vía MCP.
        """
        if self._tools_cache:
            return self._tools_cache

        # En la Arquitectura V4 pura, todas las herramientas se cargan vía MCP.
        mcp_tools = await self.mcp_provider.get_tools()
        
        # En el futuro, se podrían inyectar herramientas locales aquí
        feature_tools = [] 
        
        self._tools_cache = mcp_tools + feature_tools
        return self._tools_cache

    async def invalidate_cache(self):
        """Limpia el cache de todas las fuentes."""
        self._tools_cache = []
        await self.mcp_provider.invalidate_cache()

    async def report_tool_failure(self, tool_name: str):
        """Notifica el fallo de una herramienta para forzar re-conexión."""
        self._tools_cache = []
        await self.mcp_provider.report_tool_failure(tool_name)

    async def close(self):
        """
        Cierra todos los proveedores subyacentes.
        """
        await self.mcp_provider.close()