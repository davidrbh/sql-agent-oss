import sys
import os
import chainlit as cl
from langchain_core.messages import HumanMessage

# --- CONFIGURACIÓN DE PATH ---
# Aseguramos que el sistema pueda encontrar el paquete 'src'
# Ajustamos para incluir la carpeta actual y 'src'
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, 'src'))

# Importamos el cerebro del agente
from sql_agent.graph import build_graph

# --- EVENTOS DE CHAINLIT ---

@cl.on_chat_start
async def on_chat_start():
    """
    Se ejecuta cuando un nuevo usuario inicia una sesión.
    Aquí inicializamos el grafo y la memoria de la sesión.
    """
    # 1. Inicializar Historial
    cl.user_session.set("history", [])
    
    # 2. Cargar el Grafo
    # Gracias al Singleton implementado en 'AgentNodes', esto es muy rápido (<0.1s)
    graph = build_graph()
    cl.user_session.set("graph", graph)
    
    # 3. Bienvenida
    # Podemos usar elementos enriquecidos de Markdown
    await cl.Message(
        content="""👋 **¡Hola! Soy SQL Agent v2.1**
        
Estoy conectado a tu entorno híbrido (Base de Datos + APIs).
Puedo ayudarte a:
* 📊 Consultar datos históricos SQL.
* 🔌 Verificar estados en tiempo real vía API.
* 🔄 Corregir mis propios errores si algo falla.

_¿Qué necesitas saber hoy?_"""
    ).send()

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
        config = {"recursion_limit": 50} # Límite de seguridad
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
