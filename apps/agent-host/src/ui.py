"""
Interfaz de usuario alternativa (Legacy UI).

Este módulo mantiene una implementación de referencia para la interfaz Chainlit,
siguiendo los patrones de la arquitectura anterior para propósitos de comparación
o fallback.
"""

import sys
import os
import asyncio
import logging
import chainlit as cl
from langchain_core.messages import HumanMessage, AIMessage

from core.application.container import Container
from core.application.workflows.graph import build_graph
from features.sql_analysis.loader import get_sql_system_prompt

# Asegurar la correcta resolución de rutas para el paquete 'src'
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

logger = logging.getLogger("ui.legacy")


@cl.on_chat_start
async def on_chat_start():
    """
    Inicializa la sesión de chat legacy.
    """
    msg = cl.Message(content="🔌 Conectando con el ecosistema (Legacy Mode)...")
    await msg.send()

    try:
        tool_provider = Container.get_tool_provider()
        checkpointer_manager = Container.get_checkpointer()
        
        msg.content = "✅ Conexión establecida. Cargando herramientas..."
        await msg.update()

        tools = await tool_provider.get_tools()
        system_prompt = get_sql_system_prompt()
        
        async with checkpointer_manager.get_saver() as saver:
            graph = build_graph(tools, system_prompt, checkpointer=saver)
            cl.user_session.set("graph", graph)
            
        cl.user_session.set("history", [])

        msg.content = "👋 **SQL Agent Legacy UI activa.**"
        await msg.update()

    except Exception as e:
        logger.error(f"Error en inicio de chat legacy: {e}")
        msg.content = f"❌ **Error Fatal:** {e}"
        await msg.update()


@cl.on_chat_end
async def on_chat_end():
    """Limpieza de recursos de la sesión."""
    pass


@cl.on_message
async def on_message(message: cl.Message):
    """
    Manejador de mensajes para la UI legacy.
    """
    graph = cl.user_session.get("graph")
    history = cl.user_session.get("history")
    
    if graph is None or history is None:
        await cl.Message(content="⚠️ Error de inicialización.").send()
        return

    status_msg = cl.Message(content="🔄 _Procesando..._")
    await status_msg.send()

    final_response_msg = cl.Message(content="")
    final_answer_started = False
    full_response_text = ""

    try:
        history.append(HumanMessage(content=message.content))
        inputs = {"messages": history}
        config = {"configurable": {"thread_id": cl.context.session.id}}
        
        async for event in graph.astream_events(inputs, config=config, version="v2"):
            kind = event["event"]
            name = event.get("name", "")
            data = event.get("data", {})
            
            if kind == "on_chat_model_stream":
                node_name = event.get("metadata", {}).get("langgraph_node", "")
                if node_name == "agent" or not node_name:
                    chunk_content = data["chunk"].content
                    if chunk_content:
                        if not final_answer_started:
                            await status_msg.remove()
                            final_answer_started = True
                            await final_response_msg.send()
                        
                        await final_response_msg.stream_token(chunk_content)
                        full_response_text += chunk_content

        if not final_answer_started:
            await status_msg.remove()
            if not full_response_text:
                await cl.Message(content="✅ Completado.").send()
        else:
            await final_response_msg.update()
        
        if full_response_text:
            history.append(AIMessage(content=full_response_text))
            cl.user_session.set("history", history)
            
    except Exception as e:
        logger.error(f"Error en mensaje legacy: {e}")
        await cl.Message(content=f"❌ Error: {str(e)}").send()