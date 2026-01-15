import httpx
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from mcp import ClientSession
from mcp.client.sse import sse_client
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

# Importamos nuestro nuevo loader
from infra.mcp.loader import get_agent_tools
# Importamos el constructor del grafo
from sql_agent.graph import build_graph

# URL interna de Docker (la red que ya configuraste)
SIDECAR_URL = "http://mcp-mysql:3000"

# --- Modelo de Request ---
class ChatRequest(BaseModel):
    message: str

async def wait_for_sidecar_health(base_url: str, max_retries=15, delay=2.0):
    """Polling robusto para esperar a que Node.js termine de compilar/arrancar"""
    async with httpx.AsyncClient() as http:
        for attempt in range(max_retries):
            try:
                resp = await http.get(f"{base_url}/health", timeout=2.0)
                if resp.status_code == 200:
                    print(f"✅ Sidecar MySQL detectado y saludable (intento {attempt + 1})")
                    return True
            except Exception:
                pass
            print(f"⏳ Esperando al Sidecar... (intento {attempt + 1})")
            await asyncio.sleep(delay)
    
    raise RuntimeError("❌ Timeout crítico: El Sidecar MySQL no respondió.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Esperar salud (Health Check)
    await wait_for_sidecar_health(SIDECAR_URL)

    # 2. Conectar SSE (Handshake MCP)
    print("🔌 Iniciando conexión SSE con el Sidecar...")
    async with sse_client(url=f"{SIDECAR_URL}/sse") as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            print("🚀 Sesión MCP Establecida.")
            
            # Guardamos la sesión en el estado global
            app.state.mcp_session = session
            
            # PRE-CARGA: Verificamos que las herramientas sean visibles al arrancar
            try:
                tools = await get_agent_tools(session)
                print(f"🔧 Herramientas cargadas exitosamente: {[t.name for t in tools]}")
                
                # --- NUEVO: Inyección de Cerebro ---
                print("🧠 Construyendo grafo del agente con herramientas inyectadas...")
                agent_app = build_graph(tools)
                app.state.agent = agent_app
                print("🤖 Agente Operativo y listo para recibir chats.")
                
            except Exception as e:
                print(f"⚠️ Alerta: Conectado pero falló al inicializar agente: {e}")

            yield

    print("🛑 Desconectando sesión MCP...")

app = FastAPI(lifespan=lifespan)

# --- Endpoints ---

@app.get("/health")
async def health():
    return {"status": "ok", "agent": "running"}

@app.get("/debug/tools")
async def inspect_tools():
    """Endpoint para que tú verifiques qué ve el agente"""
    if not hasattr(app.state, "mcp_session"):
        return {"error": "No hay sesión MCP activa"}
    
    tools = await get_agent_tools(app.state.mcp_session)
    return {
        "source": "mcp-mysql-sidecar",
        "count": len(tools),
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "args_schema": t.args.get("properties") if hasattr(t, 'args') else "dynamic"
            } 
            for t in tools
        ]
    }

@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    """
    Endpoint principal para hablar con el Agente SQL.
    """
    if not hasattr(app.state, "agent"):
        raise RuntimeError("El agente no está inicializado (¿Fallo en Sidecar?)")

    # 1. Crear el mensaje de usuario
    user_message = HumanMessage(content=req.message)

    # 2. Invocar el grafo (el cerebro)
    # config={"recursion_limit": 10} evita loops infinitos si el agente se vuelve loco
    result = await app.state.agent.ainvoke(
        {"messages": [user_message]},
        config={"recursion_limit": 15}
    )

    # 3. Extraer la última respuesta del asistente
    last_message = result["messages"][-1]
    
    return {
        "response": last_message.content,
        # Opcional: devolver todo el historial si quieres debuggear en el frontend
        # "history": [m.content for m in result["messages"]]
    }
