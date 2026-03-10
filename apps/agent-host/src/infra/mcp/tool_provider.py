"""
Proveedor de herramientas basado en MCP.

Este módulo implementa la interfaz IToolProvider para descubrir, conectar y 
adaptar herramientas desde múltiples servidores MCP en el ecosistema de LangChain.
"""

import os
import logging
import asyncio
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
        
        for name in self.client.configs.keys():
            if name not in sessions:
                logger.error(f"El servidor '{name}' no tiene sesión activa aunque connect() finalizó.")
                continue
                
            session = sessions[name]
            try:
                server_tools = await asyncio.wait_for(load_mcp_tools(session), timeout=10.0)
                all_tools.extend(server_tools)
                logger.info(f"Herramientas cargadas exitosamente del servidor MCP '{name}'.")
            except asyncio.TimeoutError:
                logger.error(f"Timeout cargando herramientas del servidor MCP '{name}' (posible conexión rota o colgada).")
                # Removemos la sesión muerta de forma segura para reconectar
                await self.client.remove_session(name)
            except Exception as e:
                logger.warning(f"Error cargando herramientas del servidor MCP '{name}': {e}")
                # Forzar reconexión eliminando la sesión errónea
                await self.client.remove_session(name)
        
        self._tools_cache = all_tools
        return all_tools

    async def invalidate_cache(self):
        """Limpia el cache de herramientas para forzar un re-descubrimiento."""
        self._tools_cache = []

    async def report_tool_failure(self, tool_name: str):
        """
        Maneja el fallo de una herramienta específica invalidando el cache 
        y forzando la limpieza de sesiones.
        """
        logger.warning(f"Reportado fallo en herramienta '{tool_name}'. Invalidando cache...")
        await self.invalidate_cache()
        # Intentamos identificar qué servidor falló y removerlo
        # Por simplicidad en v1, cerramos todas para asegurar consistencia
        await self.client.close() 

    async def close(self):
        """
        Finaliza todas las conexiones MCP activas.
        """
        await self.client.close()
