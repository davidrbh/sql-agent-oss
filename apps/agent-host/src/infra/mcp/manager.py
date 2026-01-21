import asyncio
from contextlib import AsyncExitStack
from typing import Optional, Any
from mcp import ClientSession
from mcp.client.sse import sse_client
import anyio

class MCPSessionManager:
    """Gestiona la sesión del cliente MCP, incluyendo reconexión automática.

    Esta clase actúa como un wrapper sobre ClientSession de MCP, proporcionando
    resiliencia ante fallos de red o timeouts. Si una conexión se pierde,
    intentará reconectar automáticamente antes de fallar.
    """
    def __init__(self, sidecar_url: str):
        """Inicializa el manager con la URL del sidecar.

        Args:
            sidecar_url: La URL base del sidecar MCP (ej. "http://mcp-mysql:3002").
        """
        self.sidecar_url = sidecar_url
        self.session: Optional[ClientSession] = None
        self._exit_stack: Optional[AsyncExitStack] = None
        self._lock = asyncio.Lock()

    async def connect(self):
        """Establece la conexión inicial con el sidecar MCP.

        Crea y gestiona la pila de contextos asíncronos para la sesión SSE
        y la sesión del cliente MCP. Es seguro llamar a esta función múltiples
        veces; solo se conectará si no existe una sesión activa.
        """
        async with self._lock:
            if self.session:
                return
            await self._connect_unsafe()

    async def _connect_unsafe(self):
        """Método interno para establecer la conexión sin bloqueo."""
        print(f"🔄 MCP Manager: Connecting to {self.sidecar_url}...")
        self._exit_stack = AsyncExitStack()
        try:
            sse = sse_client(url=f"{self.sidecar_url}/sse", timeout=None)
            streams = await self._exit_stack.enter_async_context(sse)
            
            self.session = await self._exit_stack.enter_async_context(
                ClientSession(streams[0], streams[1])
            )
            await self.session.initialize()
            print("✅ MCP Manager: Connected and Initialized.")
        except Exception as e:
            import traceback
            print(f"❌ MCP Manager Connection Failed to {self.sidecar_url}/sse")
            print(f"   Error Type: {type(e).__name__}")
            print(f"   Error Details: {str(e)}")
            # If it's a TaskGroup error, we want to see the sub-exceptions
            if "TaskGroup" in str(e):
                 traceback.print_exc()
            await self.close()
            raise e

    async def close(self):
        """Cierra la sesión MCP y todos los recursos de red asociados.

        Realiza una limpieza explícita de la pila de contextos asíncronos.
        """
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception as e:
                print(f"⚠️ Error closing stack: {e}")
        self.session = None
        self._exit_stack = None

    async def ensure_active(self):
        """Asegura que haya una sesión activa, reconectando si es necesario."""
        if not self.session:
            await self.connect()

    async def list_tools(self) -> list:
        """Lista las herramientas disponibles en el sidecar.

        Incluye lógica de reintento: si la llamada falla por un problema de
        conexión, intentará reconectar una vez y reintentar la llamada.

        Returns:
            Una lista de herramientas disponibles en el sidecar.
        """
        await self.ensure_active()
        try:
            # We assume session exists after ensure_active
            return await self.session.list_tools()
        except Exception as e:
            print(f"⚠️ List tools failed ({e}), attempting reconnect...")
            await self.close()
            await self.connect()
            return await self.session.list_tools()

    async def call_tool(self, name: str, arguments: dict) -> Any:
        """Invoca una herramienta en el sidecar con lógica de reconexión.

        Si la llamada a la herramienta falla debido a un error de conexión,
        el manager intentará reconectar automáticamente y reintentar la llamada
        una vez.

        Args:
            name: El nombre de la herramienta a invocar.
            arguments: Un diccionario con los argumentos para la herramienta.

        Returns:
            El resultado de la invocación de la herramienta.

        Raises:
            Exception: Propaga el error original si el reintento también falla
                       o si el error no es relacionado con la conexión.
        """
        # Retry loop (max 1 retry for connection issues)
        for attempt in range(2):
            await self.ensure_active()
            try:
                return await self.session.call_tool(name, arguments=arguments)
            except Exception as e:
                # Detect specific connection errors
                is_closed = isinstance(e, (anyio.ClosedResourceError, anyio.EndOfStream, ConnectionError))
                msg = str(e).lower()
                if "closed" in msg or "connection" in msg:
                    is_closed = True

                if is_closed and attempt == 0:
                    print(f"⚠️ Connection lost during tool call '{name}'. Reconnecting...")
                    await self.close()
                    # Small backoff
                    await asyncio.sleep(0.5)
                    continue
                else:
                    # Propagate other errors (logic errors, tool errors) or if retry failed
                    raise e