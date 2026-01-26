import sys
import os
import chainlit as cl
import asyncio
from langchain_core.messages import HumanMessage, AIMessage

# --- MCP Imports ---
from mcp import ClientSession
from mcp.client.sse import sse_client
from infra.mcp.manager import MCPSessionManager

# --- FEATURE Imports (Arquitectura Híbrida) ---
# Cargamos la "feature" de Análisis SQL específicamente.
from features.sql_analysis.loader import get_sql_tools, get_sql_system_prompt

# --- CONFIGURACIÓN DE PATH ---
# Aseguramos que el sistema pueda encontrar el paquete 'src'
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, 'src'))

# Importamos el cerebro del agente
from core.application.workflows.graph import build_graph

# URL interna de Docker
SIDECAR_URL = os.getenv("SIDECAR_URL", "http://mcp-mysql:3002")

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

        # 3. Cargar Herramientas y Contexto (Feature SQL)
        # Usamos el loader específico de la feature SQL
        tools = await get_sql_tools(mcp_manager)
        system_prompt = get_sql_system_prompt()
        
        tool_names = [t.name for t in tools]
        msg.content = f"🔧 Herramientas cargadas: {tool_names}. Construyendo Cerebro..."
        await msg.update()

        # 4. Construir Grafo
        # Ahora inyectamos explícitamente el prompt y las herramientas
        graph = build_graph(tools, system_prompt)
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
    Manejador con UI "Status Bar Efímero".
    - Feedback Visual: Un mensaje que cambia dinámicamente ("🔄...", "💾...").
    - Limpieza: El mensaje de estado SE BORRA antes de mostrar la respuesta final.
    """
    graph = cl.user_session.get("graph")
    history = cl.user_session.get("history")
    
    if graph is None or history is None:
        await cl.Message(content="⚠️ No se puede procesar el mensaje porque la conexión inicial con el Sidecar falló. Por favor, revisa los logs y reinicia el chat.").send()
        return

    # 1. Mensaje de Estado (Ephemeral Status Bar)
    status_msg = cl.Message(content="🔄 _Iniciando..._")
    await status_msg.send()

    # Contenedor para respuesta final
    final_response_msg = cl.Message(content="")
    final_answer_started = False
    full_response_text = ""

    try:
        # Añadir mensaje del usuario al historial
        history.append(HumanMessage(content=message.content))
        inputs = {"messages": history}
        config = {"configurable": {"thread_id": cl.context.session.id}}
        
        async for event in graph.astream_events(inputs, config=config, version="v2"):
            kind = event["event"]
            name = event.get("name", "")
            data = event.get("data", {})
            
            # --- 2. FEEDBACK VISUAL (Status Bar) ---
            if kind == "on_chain_start":
                if name == "intent_classifier_node":
                    status_msg.content = "🚦 _Clasificando Intención..._"
                    await status_msg.update()
                    await asyncio.sleep(0.7) # Smooth transition
                elif name == "sql_validator_node":
                    status_msg.content = "🛡️ _Validando Seguridad SQL..._"
                    await status_msg.update()
                    await asyncio.sleep(0.7) # Smooth transition
                elif name == "agent": # FIX: Nombre real del nodo es 'agent'
                    status_msg.content = "🧠 _Generando Respuesta..._"
                    await status_msg.update()
                    await asyncio.sleep(0.7) # Smooth transition
                    
            elif kind == "on_tool_start":
                status_msg.content = f"🛠️ _Ejecutando Herramienta: {name}..._"
                await status_msg.update()
                await asyncio.sleep(0.7) # Smooth transition
                
            elif kind == "on_tool_end":
                status_msg.content = "✅ _Datos obtenidos. Procesando..._"
                await status_msg.update()
                await asyncio.sleep(0.7) # Smooth transition

            # --- 3. STREAMING RESPUESTA FINAL ---
            elif kind == "on_chat_model_stream":
                # Verificamos origen. Metadata suele tener 'langgraph_node'
                node_name = event.get("metadata", {}).get("langgraph_node", "")
                
                # 'agent' es el nodo que habla con el usuario final.
                # 'intent_classifier' tambien usa LLM pero es interno.
                if node_name == "agent" or not node_name:
                    chunk_content = data["chunk"].content
                    if chunk_content:
                        if not final_answer_started:
                            # Primer token: borramos status y mostramos respuesta
                            await status_msg.remove()
                            final_answer_started = True
                            await final_response_msg.send()
                        
                        await final_response_msg.stream_token(chunk_content)
                        full_response_text += chunk_content

        # --- 4. FINALIZACIÓN ---
        
        if not final_answer_started:
            # Fallback: Si no hubo streaming (ej. respuesta muy corta o error en stream),
            # verificamos si el grafo devolvió algo en el último estado.
            # Como astream_events iteró, el último estado está 'implícito'.
            # Para simplificar, si no hubo stream, borramos status y enviamos mensaje genérico o error.
            await status_msg.remove()
            if not full_response_text:
                await cl.Message(content="✅ Proceso completado (Sin respuesta de texto generada).").send()
        else:
            await final_response_msg.update()
        
        # Guardar en historial la respuesta completa del asistente
        if full_response_text:
            history.append(AIMessage(content=full_response_text))
            cl.user_session.set("history", history)
            
    except Exception as e:
        # Error handling
        if not final_answer_started:
            status_msg.content = f"❌ **Error:** {str(e)}"
            await status_msg.update()
        else:
            await cl.Message(content=f"❌ **Error ocurrido durante la respuesta:** {str(e)}").send()
        print(f"Error en on_message: {e}")
