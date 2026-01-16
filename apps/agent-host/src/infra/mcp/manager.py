import asyncio
from contextlib import AsyncExitStack
from typing import Optional, Any
from mcp import ClientSession
from mcp.client.sse import sse_client
import anyio

class MCPSessionManager:
    """
    Wrapper around MCP ClientSession that handles auto-reconnection
    on network failures or timeouts.
    """
    def __init__(self, sidecar_url: str):
        self.sidecar_url = sidecar_url
        self.session: Optional[ClientSession] = None
        self._exit_stack: Optional[AsyncExitStack] = None
        self._lock = asyncio.Lock()

    async def connect(self):
        """Initial connection."""
        async with self._lock:
            if self.session:
                return
            await self._connect_unsafe()

    async def _connect_unsafe(self):
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
            print(f"❌ MCP Manager Connection Failed: {e}")
            await self.close()
            raise e

    async def close(self):
        """Explicit cleanup."""
        # Lock to ensure we don't close while connecting in another task
        # But for simplicity, we just clean up.
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except Exception as e:
                print(f"⚠️ Error closing stack: {e}")
        self.session = None
        self._exit_stack = None

    async def ensure_active(self):
        """Check connection or reconnect if needed."""
        if not self.session:
            await self.connect()

    async def list_tools(self):
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
        """
        Calls a tool with auto-reconnect logic.
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
