"""Punto de entrada principal para la interfaz de usuario (Chainlit).

Este módulo gestiona la lógica de la conversación mediante Web UI, integrando
el núcleo del agente, el descubrimiento de herramientas y la persistencia
del estado en PostgreSQL.
"""

import sys
import os
import asyncio
import logging
import chainlit as cl
from langchain_core.messages import HumanMessage, AIMessage

from core.application.container import Container
from core.application.workflows.graph import build_graph
from features.sheets_analysis.loader import get_sheets_system_prompt

# Asegurar la correcta resolución de rutas para el paquete 'src'
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

logger = logging.getLogger("ui.main")


@cl.on_chat_start
async def on_chat_start():
    """
    Inicializa la sesión de chat, cargando herramientas y configurando el grafo.
    """
    msg = cl.Message(content="🔌 Conectando con el ecosistema de micro-agentes (MCP)...")
    await msg.send()

    try:
        # Obtener dependencias desde el contenedor global
        tool_provider = Container.get_tool_provider()
        checkpointer_manager = Container.get_checkpointer()
        
        msg.content = "✅ Conexión establecida. Cargando herramientas y memoria..."
        await msg.update()

        tools = await tool_provider.get_tools()
        system_prompt = get_sheets_system_prompt(channel="web")
        
        tool_names = [t.name for t in tools]
        msg.content = f"🔧 Herramientas cargadas: {tool_names}. Configurando persistencia..."
        await msg.update()

        # Construcción del grafo con persistencia transaccional
        async with checkpointer_manager.get_saver() as saver:
            graph = build_graph(tools, system_prompt, checkpointer=saver)
            cl.user_session.set("graph", graph)
            
        cl.user_session.set("history", [])

        msg.content = f"""👋 **¡Hola! Soy tu Agente de Análisis de Datos**

Herramientas activas: `{', '.join(tool_names) if tool_names else 'ninguna'}`

Puedo ayudarte a:
* 📊 Consultar y analizar hojas de cálculo de Google Sheets.
* 🗄️ Ejecutar consultas en bases de datos relacionales (SQL).
* 🔌 Integrarme con múltiples servicios vía MCP.
* 💾 Mantener el contexto de la conversación entre sesiones.

_¿Qué consulta deseas realizar?_"""
        await msg.update()

    except Exception as e:
        logger.error(f"Error fatal en inicio de chat: {e}")
        msg.content = f"❌ **Error Fatal:** No se pudo inicializar el entorno.\n\nError: {e}"
        await msg.update()


@cl.on_chat_end
async def on_chat_end():
    """
    Gestiona la limpieza de recursos al finalizar la sesión.
    Nota: Los recursos globales persisten en el Container para su reutilización.
    """
    pass


@cl.on_message
async def on_message(message: cl.Message):
    """
    Manejador principal de mensajes con soporte para streaming y feedback visual.
    """
    graph = cl.user_session.get("graph")
    history = cl.user_session.get("history")
    
    if graph is None or history is None:
        await cl.Message(content="⚠️ Error de conexión inicial. Reinicia el chat.").send()
        return

    status_msg = cl.Message(content="🔄 _Iniciando..._")
    await status_msg.send()

    final_response_msg = cl.Message(content="")
    final_answer_started = False
    full_response_text = ""

    try:
        # Añadir mensaje actual al historial
        history.append(HumanMessage(content=message.content))
        
        inputs = {"messages": history}
        config = {
            "configurable": {"thread_id": cl.context.session.id},
            "recursion_limit": 50
        }
        
        async for event in graph.astream_events(inputs, config=config, version="v2"):
            kind = event["event"]
            name = event.get("name", "")
            data = event.get("data", {})
            
            # Gestión de la barra de estado efímera
            if kind == "on_chain_start":
                if name == "intent_classifier_node":
                    status_msg.content = "🚦 _Clasificando Intención..._"
                    await status_msg.update()
                elif name == "agent":
                    status_msg.content = "🧠 _Generando Respuesta..._"
                    await status_msg.update()
                    
            elif kind == "on_tool_start":
                status_msg.content = f"🛠️ _Ejecutando Herramienta: {name}..._"
                await status_msg.update()
                
            elif kind == "on_tool_end":
                status_msg.content = "✅ _Procesando resultados..._"
                await status_msg.update()

            # Streaming de la respuesta final del modelo
            elif kind == "on_chat_model_stream":
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
                await cl.Message(content="✅ Proceso completado.").send()
        else:
            await final_response_msg.update()
        
        if full_response_text:
            history.append(AIMessage(content=full_response_text))
            cl.user_session.set("history", history)
            
    except Exception as e:
        logger.error(f"Error procesando mensaje: {e}")
        if not final_answer_started:
            status_msg.content = f"❌ **Error:** {str(e)}"
            await status_msg.update()
        else:
            await cl.Message(content="❌ Ocurrió un error durante la respuesta.").send()