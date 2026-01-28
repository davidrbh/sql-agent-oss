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
import httpx
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
    """

    def __init__(self, config_json: str):
        self.configs: Dict[str, ServerConfig] = self._parse_config(config_json)
        self.sessions: Dict[str, ClientSession] = {}
        # Manejamos un ExitStack por cada servidor para permitir re-conexiones individuales
        self.stacks: Dict[str, AsyncExitStack] = {}
        self._lock = asyncio.Lock()
        # Tiempos de espera estándar (60s)
        self._timeout_sec = 60.0

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
        """Conecta a un servidor específico y registra su sesión en su propio ExitStack."""
        logger.info(f"Conectando al servidor MCP '{name}' vía {config.transport}...")
        
        # Crear un nuevo stack para esta conexión
        stack = AsyncExitStack()
        
        try:
            if config.transport == "sse":
                if not config.url:
                    raise ValueError(f"Falta URL para el servidor SSE '{name}'")
                
                ctx = sse_client(
                    url=config.url, 
                    timeout=self._timeout_sec,
                    sse_read_timeout=self._timeout_sec
                )
                read_stream, write_stream = await stack.enter_async_context(ctx)
                
                session = ClientSession(read_stream, write_stream)
                await stack.enter_async_context(session)
                
                await session.initialize()
                self.sessions[name] = session
                self.stacks[name] = stack
                logger.info(f"✅ Conectado a '{name}' (SSE)")
            
            elif config.transport == "stdio":
                if not config.command:
                    raise ValueError(f"Falta comando para el servidor Stdio '{name}'")
                
                server_params = StdioServerParameters(
                    command=config.command,
                    args=config.args or [],
                    env={**os.environ, **(config.env or {})}
                )
                
                ctx = stdio_client(server_params)
                read_stream, write_stream = await stack.enter_async_context(ctx)
                
                session = ClientSession(read_stream, write_stream)
                await stack.enter_async_context(session)
                
                await session.initialize()
                self.sessions[name] = session
                self.stacks[name] = stack
                logger.info(f"✅ Conectado a '{name}' (Stdio)")
            
        except Exception as e:
            logger.error(f"❌ Error conectando con '{name}': {repr(e)}")
            await stack.aclose() # Limpiar si falla

    async def _remove_session_internal(self, name: str):
        """Lógica interna de limpieza sin bloqueos (usar solo dentro de async with self._lock)."""
        if name in self.stacks:
            logger.warning(f"Cerrando sesión expirada o rota: '{name}'")
            try:
                # Forzamos un timeout al cerrar para que una sesión colgada no bloquee todo el Agente
                await asyncio.wait_for(self.stacks[name].aclose(), timeout=5.0)
            except Exception as e:
                logger.error(f"Error (no crítico) cerrando stack para '{name}': {repr(e)}")
            finally:
                # Nos aseguramos de limpiar las referencias pase lo que pase
                self.stacks.pop(name, None)
                self.sessions.pop(name, None)

    async def remove_session(self, name: str):
        """Cierra y elimina una sesión específica, permitiendo su reconexión posterior."""
        async with self._lock:
            await self._remove_session_internal(name)

    async def close(self):
        """Libera todos los recursos y cierra todas las sesiones MCP."""
        logger.info("Cerrando todas las conexiones MCP...")
        async with self._lock:
            # Creamos una lista de nombres para evitar modificar el dict mientras iteramos
            for name in list(self.stacks.keys()):
                await self._remove_session_internal(name)
            logger.info("Conexiones MCP cerradas limpiamente.")
