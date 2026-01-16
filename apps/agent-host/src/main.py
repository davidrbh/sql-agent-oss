import sys
import os
import chainlit as cl
from langchain_core.messages import HumanMessage

# --- MCP Imports ---
from mcp import ClientSession
from mcp.client.sse import sse_client
from infra.mcp.loader import get_agent_tools
from infra.mcp.manager import MCPSessionManager

# --- CONFIGURACIÓN DE PATH ---
# Aseguramos que el sistema pueda encontrar el paquete 'src'
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, 'src'))

# Importamos el cerebro del agente
from agent_core.graph import build_graph

# URL interna de Docker
SIDECAR_URL = os.getenv("SIDECAR_URL", "http://mcp-mysql:3000")

# --- EVENTOS DE CHAINLIT ---

@cl.on_chat_start
async def on_chat_start():
    """
    Se ejecuta cuando un nuevo usuario inicia una sesión.
    Aquí inicializamos la conexión MCP, cargamos herramientas y construimos el grafo.
    """
    
    # 1. Feedback inicial
    msg = cl.Message(content="🔌 Conectando con el Sidecar MySQL (MCP Protocol)...")
    await msg.send()

    try:
        # 2. Inicializar Conexión MCP Persistente (Auto-Reconnect)
        # Usamos MCPSessionManager para manejar reconexiones automáticas si el socket se cierra.
        mcp_manager = MCPSessionManager(SIDECAR_URL)
        await mcp_manager.connect()
        
        cl.user_session.set("mcp_manager", mcp_manager)
        
        msg.content = "✅ Conexión MCP Establecida. Cargando herramientas..."
        await msg.update()

        # 3. Cargar Herramientas
        # Pasamos el manager en lugar de la session cruda.
        # El loader debe aceptar este objeto duck-typed (tiene .call_tool y .list_tools)
        tools = await get_agent_tools(mcp_manager)
        
        tool_names = [t.name for t in tools]
        msg.content = f"🔧 Herramientas cargadas: {tool_names}. Construyendo Cerebro..."
        await msg.update()

        # 4. Construir Grafo
        graph = build_graph(tools)
        cl.user_session.set("graph", graph)
        cl.user_session.set("history", [])

        # 5. Bienvenida Final
        msg.content = """👋 **¡Hola! Soy SQL Agent v2.1**
        
Estoy conectado a tu entorno híbrido (Base de Datos + APIs).
Puedo ayudarte a:
* 📊 Consultar datos históricos SQL.
* 🔌 Verificar estados en tiempo real vía API.
* 🔄 Corregir mis propios errores si algo falla.

_¿Qué necesitas saber hoy?_"""
        await msg.update()

    except Exception as e:
        msg.content = f"❌ **Error Fatal:** No se pudo conectar al Sidecar.\n\nError: {e}"
        await msg.update()

@cl.on_chat_end
async def on_chat_end():
    """Limpieza de recursos al cerrar la pestaña"""
    # 1. Cerrar Cliente MCP
    manager = cl.user_session.get("mcp_manager")
    if manager:
        await manager.close()
        try:
            await client.__aexit__(None, None, None)
        except Exception as e:
            print(f"Error cerrando Cliente MCP: {e}")

    # 2. Cerrar Transporte SSE
    sse_ctx = cl.user_session.get("sse_ctx")
    if sse_ctx:
        print("🛑 Cerrando conexión MCP...")
        try:
            await sse_ctx.__aexit__(None, None, None)
        except Exception as e:
            print(f"Error cerrando SSE: {e}")

@cl.on_message
async def on_message(message: cl.Message):
    """
    Manejador principal de mensajes.
    Recibe el input del usuario e invoca al agente.
    """
    # Recuperar estado
    graph = cl.user_session.get("graph")
    history = cl.user_session.get("history")
    
    # Placeholder de carga
    msg = cl.Message(content="")
    await msg.send()
    
    try:
        # Añadir mensaje de usuario al historial local (LangGraph espera esto)
        history.append(HumanMessage(content=message.content))
        
        inputs = {
            "question": message.content,
            "messages": history
        }
        
        # Feedback visual
        msg.content = "🔄 _Analizando intención y ejecutando herramientas..._"
        await msg.update()
        
        # Ejecución del Grafo (Async)
        config = {"recursion_limit": 150} # Límite de seguridad aumentado
        result = await graph.ainvoke(inputs, config=config)
        
        # Actualizar historial con lo que devolvió el agente (incluye ToolMessages, AIMessages, etc)
        new_history = result["messages"]
        cl.user_session.set("history", new_history)
        
        # Extraer última respuesta del asistente
        # LangGraph devuelve toda la lista, el último debe ser AIMessage
        final_response_content = new_history[-1].content
        
        # Enviar respuesta final
        msg.content = final_response_content
        await msg.update()
        
    except Exception as e:
        error_msg = f"❌ **Error Crítico:**\n\n```\n{str(e)}\n```"
        msg.content = error_msg
        await msg.update()
        print(f"Error en Chainlit handler: {e}")
