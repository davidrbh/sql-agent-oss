import asyncio
import json
import os
import logging
from contextlib import AsyncExitStack
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

logger = logging.getLogger(__name__)

@dataclass
class ServerConfig:
    """Configuración para una conexión con un servidor MCP."""
    transport: str  # "stdio" o "sse"
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    url: Optional[str] = None

class MultiServerMCPClient:
    """
    Cliente para gestionar múltiples conexiones a servidores MCP simultáneamente.
    
    Maneja el ciclo de vida de múltiples sesiones MCP, proporcionando una interfaz 
    unificada para el descubrimiento y ejecución de herramientas a través de diferentes transportes.
    """

    def __init__(self, config_json: str):
        """
        Inicializa el cliente multi-servidor.

        Args:
            config_json: Una cadena JSON que contiene las configuraciones de los servidores.
        """
        self.configs: Dict[str, ServerConfig] = self._parse_config(config_json)
        self.sessions: Dict[str, ClientSession] = {}
        self._exit_stack = AsyncExitStack()
        self._lock = asyncio.Lock()

    def get_sessions(self) -> Dict[str, ClientSession]:
        """
        Retorna el diccionario de sesiones MCP activas.
        
        Returns:
            Dict[str, ClientSession]: Sesiones activas indexadas por nombre del servidor.
        """
        return self.sessions

    def _parse_config(self, config_json: str) -> Dict[str, ServerConfig]:
        """Parsea la configuración JSON en objetos ServerConfig."""
        try:
            data = json.loads(config_json)
            configs = {}
            for name, cfg in data.items():
                configs[name] = ServerConfig(**cfg)
            return configs
        except Exception as e:
            logger.error(f"Error parseando MCP_SERVERS_CONFIG: {e}")
            return {}

    async def connect(self):
        """Establece conexiones con todos los servidores MCP configurados."""
        async with self._lock:
            for name, config in self.configs.items():
                if name in self.sessions:
                    continue
                await self._connect_server(name, config)

    async def _connect_server(self, name: str, config: ServerConfig):
        """Conecta a un único servidor MCP basado en su tipo de transporte."""
        logger.info(f"Conectando al servidor MCP '{name}' vía {config.transport}...")
        try:
            if config.transport == "sse":
                if not config.url:
                    raise ValueError(f"Falta URL para el servidor SSE '{name}'")
                # Transporte SSE
                ctx = sse_client(url=config.url)
                streams = await self._exit_stack.enter_async_context(ctx)
                session = await self._exit_stack.enter_async_context(ClientSession(streams[0], streams[1]))
            
            elif config.transport == "stdio":
                if not config.command:
                    raise ValueError(f"Falta comando para el servidor Stdio '{name}'")
                # Transporte Stdio
                server_params = StdioServerParameters(
                    command=config.command,
                    args=config.args or [],
                    env={**os.environ, **(config.env or {})}
                )
                ctx = stdio_client(server_params)
                streams = await self._exit_stack.enter_async_context(ctx)
                session = await self._exit_stack.enter_async_context(ClientSession(streams[0], streams[1]))
            
            else:
                raise ValueError(f"Transporte no soportado '{config.transport}' para el servidor '{name}'")

            await session.initialize()
            self.sessions[name] = session
            logger.info(f"Conectado a '{name}'")
            
        except Exception as e:
            logger.error(f"Falló la conexión a '{name}': {e}")

    async def list_all_tools(self) -> Dict[str, List[Any]]:
        """
        Lista las herramientas de todos los servidores conectados.

        Returns:
            Dict mapeando nombres de servidores a su lista de herramientas.
        """
        all_tools = {}
        for name, session in self.sessions.items():
            try:
                result = await session.list_tools()
                all_tools[name] = result.tools
            except Exception as e:
                logger.warning(f"Falló listar herramientas para '{name}': {e}")
        return all_tools

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Invoca una herramienta en un servidor específico.

        Args:
            server_name: El nombre del servidor que aloja la herramienta.
            tool_name: El nombre de la herramienta a ejecutar.
            arguments: Argumentos para la herramienta.
        """
        session = self.sessions.get(server_name)
        if not session:
            raise ValueError(f"Servidor '{server_name}' no conectado")
        
        return await session.call_tool(tool_name, arguments=arguments)

    async def close(self):
        """Cierra todas las sesiones activas y pilas de recursos."""
        await self._exit_stack.aclose()
        self.sessions.clear()
        logger.info("Todas las conexiones MCP cerradas.")