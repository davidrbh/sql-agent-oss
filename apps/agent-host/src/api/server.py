# apps/agent-host/src/api/server.py
import httpx
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from mcp import ClientSession
from mcp.client.sse import sse_client

# Configuración
SIDECAR_URL = "http://mcp-mysql:3000"  # Sin /sse para el health check

async def wait_for_sidecar_health(base_url: str, max_retries=10, delay=2.0):
    """
    Bloquea el arranque del Agente hasta que el Brazo (Sidecar) responda al ping.
    """
    async with httpx.AsyncClient() as http:
        for attempt in range(max_retries):
            try:
                # 1. Llamamos al endpoint que creaste
                resp = await http.get(f"{base_url}/health", timeout=2.0)
                if resp.status_code == 200:
                    print(f"✅ Sidecar MySQL listo (intento {attempt + 1})")
                    return True
            except Exception as e:
                print(f"⏳ Esperando al Sidecar MySQL... ({e})")
            
            await asyncio.sleep(delay)
    
    raise RuntimeError("❌ El Sidecar MySQL no arrancó a tiempo. Abortando.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. FASE DE ESPERA (La pieza que faltaba)
    # Antes de intentar conectar SSE, verificamos salud.
    await wait_for_sidecar_health(SIDECAR_URL)

    # 2. FASE DE CONEXIÓN
    # Ahora es seguro conectar porque sabemos que Fastify está escuchando
    async with sse_client(url=f"{SIDECAR_URL}/sse") as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            print("🚀 Conectado a MCP MySQL via SSE")
            await session.initialize()
            
            # Guardar en estado
            app.state.mcp_mysql = session
            yield

    print("🛑 Desconectando MCP...")

app = FastAPI(lifespan=lifespan)
