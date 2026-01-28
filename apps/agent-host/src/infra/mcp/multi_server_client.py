"""
Cliente de conexión para múltiples servidores MCP.

Maneja el ciclo de vida de las sesiones MCP (SSE y Stdio), proporcionando
una interfaz unificada y resiliente para la ejecución de herramientas.
Utiliza AsyncExitStack para una gestión de recursos segura y profesional.
"""

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
    Gestiona múltiples conexiones a servidores MCP de forma centralizada.
    
    Esta clase es responsable de mantener activas las sesiones con los sidecars
    y asegurar que todos los recursos se liberen correctamente al apagar el sistema.
    """

    def __init__(self, config_json: str):
        self.configs: Dict[str, ServerConfig] = self._parse_config(config_json)
        self.sessions: Dict[str, ClientSession] = {}
        # El ExitStack centraliza el ciclo de vida de todos los transportes y sesiones
        self._exit_stack = AsyncExitStack()
        self._lock = asyncio.Lock()

    def _parse_config(self, config_json: str) -> Dict[str, ServerConfig]:
        try:
            data = json.loads(config_json)
            configs = {}
            for name, cfg in data.items():
                configs[name] = ServerConfig(**cfg)
            return configs
        except Exception as e:
            logger.error(f"Error parseando MCP_SERVERS_CONFIG: {e}")
            return {}

    def get_sessions(self) -> Dict[str, ClientSession]:
        return self.sessions

    async def connect(self):
        """Establece conexiones con todos los servidores configurados si aún no existen."""
        async with self._lock:
            for name, config in self.configs.items():
                if name not in self.sessions:
                    await self._connect_server(name, config)

    async def _connect_server(self, name: str, config: ServerConfig):
        """Conecta a un servidor específico y registra su sesión en el ExitStack."""
        logger.info(f"Conectando al servidor MCP '{name}' vía {config.transport}...")
        try:
            if config.transport == "sse":
                if not config.url:
                    raise ValueError(f"Falta URL para el servidor SSE '{name}'")
                
                # 1. Entrar al contexto del transporte SSE
                ctx = sse_client(url=config.url)
                read_stream, write_stream = await self._exit_stack.enter_async_context(ctx)
                
                # 2. Crear y entrar al contexto de la sesión MCP
                session = ClientSession(read_stream, write_stream)
                await self._exit_stack.enter_async_context(session)
                
                # 3. Inicializar el protocolo
                await session.initialize()
                self.sessions[name] = session
                logger.info(f"✅ Conectado a '{name}' (SSE)")
            
            elif config.transport == "stdio":
                if not config.command:
                    raise ValueError(f"Falta comando para el servidor Stdio '{name}'")
                
                server_params = StdioServerParameters(
                    command=config.command,
                    args=config.args or [],
                    env={**os.environ, **(config.env or {})}
                )
                
                # 1. Entrar al contexto del transporte Stdio
                ctx = stdio_client(server_params)
                read_stream, write_stream = await self._exit_stack.enter_async_context(ctx)
                
                # 2. Crear y entrar al contexto de la sesión MCP
                session = ClientSession(read_stream, write_stream)
                await self._exit_stack.enter_async_context(session)
                
                # 3. Inicializar el protocolo
                await session.initialize()
                self.sessions[name] = session
                logger.info(f"✅ Conectado a '{name}' (Stdio)")
            
        except Exception as e:
            logger.error(f"❌ Error conectando con '{name}': {repr(e)}")

    async def close(self):
        """Libera todos los recursos y cierra todas las sesiones MCP."""
        logger.info("Cerrando todas las conexiones MCP...")
        try:
            # aclose() ejecutará los __aexit__ de todos los contextos en orden inverso
            await self._exit_stack.aclose()
            self.sessions.clear()
            logger.info("Conexiones MCP cerradas limpiamente.")
        except Exception as e:
            # Evitamos que fallos en el cierre bloqueen el shutdown del proceso
            logger.error(f"Error durante el cierre de MCP: {repr(e)}")
