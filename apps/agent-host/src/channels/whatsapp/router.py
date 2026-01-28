"""
Router de FastAPI para el canal de WhatsApp mediante el gateway WAHA.

Este módulo gestiona la recepción de mensajes vía webhooks, la orquestación 
del procesamiento mediante el núcleo del agente y el envío de respuestas
de vuelta a WhatsApp. Utiliza la arquitectura V4 con persistencia en PostgreSQL.
"""

import logging
import os
from typing import Dict, Any

import httpx
from fastapi import APIRouter, Request, BackgroundTasks
from langchain_core.messages import HumanMessage

from core.application.container import Container
from core.application.workflows.graph import build_graph
from features.sql_analysis.loader import get_sql_system_prompt

logger = logging.getLogger("channels.whatsapp")

router = APIRouter(tags=["Canal WhatsApp"])

WAHA_BASE_URL = os.getenv("WAHA_BASE_URL", "http://waha:3000")
WAHA_API_KEY = os.getenv("WAHA_API_KEY")

STATUS_BROADCAST_ID = "status@broadcast"


async def start_typing(chat_id: str) -> None:
    """
    Envía una señal de 'escribiendo...' al chat de WhatsApp.

    Args:
        chat_id: Identificador único del chat de WhatsApp.
    """
    url = f"{WAHA_BASE_URL}/api/startTyping"
    headers = {"Content-Type": "application/json"}
    
    if WAHA_API_KEY:
        headers["X-Api-Key"] = WAHA_API_KEY
    
    payload = {"session": "default", "chatId": chat_id}
    
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload, headers=headers, timeout=2.0)
    except Exception as e:
        logger.warning(f"[WhatsApp] Fallo al enviar indicador de escritura: {str(e)}")


async def send_whatsapp_message(chat_id: str, text: str) -> None:
    """
    Envía un mensaje de texto al chat de WhatsApp vía WAHA.

    Args:
        chat_id: Identificador único del chat de WhatsApp.
        text: Contenido del mensaje a enviar.
    """
    headers = {"Content-Type": "application/json"}
    if WAHA_API_KEY:
        headers["X-Api-Key"] = WAHA_API_KEY

    payload = {
        "chatId": chat_id, 
        "text": text, 
        "session": "default"
    }

    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"[WhatsApp] Enviando respuesta a {chat_id}...")
            response = await client.post(
                f"{WAHA_BASE_URL}/api/sendText",
                json=payload,
                headers=headers,
                timeout=20.0
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"[WhatsApp] Mensaje entregado exitosamente.")
            else:
                logger.error(
                    f"[WhatsApp] Fallo al enviar mensaje. "
                    f"Estado: {response.status_code}, Respuesta: {response.text}"
                )
    except Exception as e:
        logger.error(f"[WhatsApp] Error de conexión al enviar mensaje: {str(e)}")


async def process_message(chat_id: str, message_text: str) -> None:
    """
    Orquesta el procesamiento de un mensaje de WhatsApp.

    Obtiene las herramientas y el motor de persistencia del contenedor global,
    invoca al agente de IA y envía la respuesta generada.

    Args:
        chat_id: Identificador del chat.
        message_text: Texto enviado por el usuario.
    """
    try:
        logger.info(f"[WhatsApp] Procesando mensaje de {chat_id}...")
        await start_typing(chat_id)
        
        tool_provider = Container.get_tool_provider()
        checkpointer_manager = Container.get_checkpointer()
        
        tools = await tool_provider.get_tools()
        system_prompt = get_sql_system_prompt(channel="whatsapp")
        
        async with checkpointer_manager.get_saver() as saver:
            agent = build_graph(
                tools=tools, 
                system_prompt=system_prompt, 
                checkpointer=saver
            )
            
            config = {
                "configurable": {
                    "thread_id": f"whatsapp_{chat_id}"
                },
                "recursion_limit": 50
            }
            
            inputs = {"messages": [HumanMessage(content=message_text)]}
            
            logger.info("[WhatsApp] Invocando Agente de IA...")
            result = await agent.ainvoke(inputs, config=config)
            
            bot_response = result["messages"][-1].content
            await send_whatsapp_message(chat_id, bot_response)

    except Exception as e:
        logger.error(f"[WhatsApp] Error crítico en el procesamiento: {str(e)}")
        await send_whatsapp_message(chat_id, "Lo siento, ocurrió un error interno procesando tu solicitud.")


@router.post("/webhook")
async def whatsapp_webhook(
    request: Request, 
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Manejador de webhooks para eventos entrantes de WAHA.

    Filtra los mensajes para ignorar eventos de estado o mensajes propios
    y encola el procesamiento válido como una tarea en segundo plano.

    Args:
        request: Objeto de petición de FastAPI.
        background_tasks: Gestor de tareas en segundo plano.

    Returns:
        Dict: Estado del procesamiento del webhook.
    """
    try:
        data = await request.json()
        
        if data.get("event") != "message":
            return {"status": "ignored", "reason": "invalid_event_type"}
            
        payload = data.get("payload", {})
        
        if payload.get("fromMe"):
            return {"status": "ignored", "reason": "from_me"}
            
        chat_id = payload.get("chatId") or payload.get("from")
        sender_id = payload.get("from")
        body = payload.get("body")

        if chat_id == STATUS_BROADCAST_ID or sender_id == STATUS_BROADCAST_ID:
            return {"status": "ignored", "reason": "status_broadcast"}

        if chat_id and body:
            logger.info(f"[WhatsApp Webhook] Mensaje recibido de {chat_id}. Encolando...")
            background_tasks.add_task(process_message, chat_id, body)
            return {"status": "processing"}
        
        return {"status": "ignored", "reason": "missing_data"}

    except Exception as e:
        logger.error(f"[WhatsApp Webhook] Error al parsear payload: {str(e)}")
        return {"status": "error", "message": str(e)}