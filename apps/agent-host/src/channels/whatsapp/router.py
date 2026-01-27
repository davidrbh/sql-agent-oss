import logging
import os
from typing import Dict, Any

import httpx
from fastapi import APIRouter, Request, BackgroundTasks
from langchain_core.messages import HumanMessage

# --- ARQUITECTURA V4: IMPORTAMOS EL NÚCLEO ---
from core.application.container import Container
from core.application.workflows.graph import build_graph
from features.sql_analysis.loader import get_sql_system_prompt

# Configuración del logger a nivel de módulo
logger = logging.getLogger("channels.whatsapp")

router = APIRouter(tags=["Canal WhatsApp"])

# --- Constantes de Configuración ---
WAHA_BASE_URL = os.getenv("WAHA_BASE_URL", "http://waha:3000")
WAHA_API_KEY = os.getenv("WAHA_API_KEY")

# ID especial de WhatsApp para actualizaciones de estado (Historias)
STATUS_BROADCAST_ID = "status@broadcast"


async def start_typing(chat_id: str) -> None:
    """
    Envía una señal de 'escribiendo...' al chat de WhatsApp especificado vía WAHA.
    """
    url = f"{WAHA_BASE_URL}/api/startTyping"
    headers = {"Content-Type": "application/json"}
    
    if WAHA_API_KEY:
        headers["X-Api-Key"] = WAHA_API_KEY
    
    payload = {"session": "default", "chatId": chat_id}
    
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload, headers=headers, timeout=2.0)
            # logger.debug(f"[WhatsApp] Indicador de escritura enviado a {chat_id}")
    except Exception as e:
        logger.warning(f"[WhatsApp] Fallo al enviar indicador de escritura: {str(e)}")


async def send_whatsapp_message(chat_id: str, text: str) -> None:
    """
    Envía un mensaje de texto final al chat de WhatsApp especificado vía WAHA.
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
    Procesa el mensaje usando la arquitectura V4 (Container + Postgres).
    """
    try:
        logger.info(f"[WhatsApp] Procesando mensaje de {chat_id}...")
        await start_typing(chat_id)
        
        # 1. Obtener recursos del Contenedor (Singleton)
        tool_provider = Container.get_tool_provider()
        checkpointer_manager = Container.get_checkpointer()
        
        # 2. Cargar Herramientas y Contexto
        tools = await tool_provider.get_tools()
        system_prompt = get_sql_system_prompt()
        
        # 3. Construir Grafo con Persistencia PostgreSQL
        async with checkpointer_manager.get_saver() as saver:
            agent = build_graph(
                tools=tools, 
                system_prompt=system_prompt, 
                checkpointer=saver
            )
            
            # Configuración de sesión persistente
            config = {
                "configurable": {
                    "thread_id": f"whatsapp_{chat_id}" # Prefijo para evitar colisiones
                },
                "recursion_limit": 50
            }
            
            # Invocación
            inputs = {"messages": [HumanMessage(content=message_text)]}
            
            logger.info("[WhatsApp] Invocando Agente de IA (Persistencia Postgres)...")
            result = await agent.ainvoke(inputs, config=config)
            
            # Extraer respuesta
            bot_response = result["messages"][-1].content
            await send_whatsapp_message(chat_id, bot_response)

    except Exception as e:
        logger.error(f"[WhatsApp] Error crítico: {str(e)}")
        import traceback
        traceback.print_exc()
        await send_whatsapp_message(chat_id, "Lo siento, ocurrió un error interno procesando tu solicitud.")


@router.post("/webhook")
async def whatsapp_webhook(
    request: Request, 
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Endpoint para recibir webhooks del servicio WAHA.
    """
    try:
        data = await request.json()
        
        # 1. Validar Tipo de Evento
        if data.get("event") != "message":
            return {"status": "ignored", "reason": "invalid_event_type"}
            
        payload = data.get("payload", {})
        
        # 2. Filtro: Mensajes propios (evitar bucles infinitos)
        if payload.get("fromMe"):
            return {"status": "ignored", "reason": "from_me"}
            
        # 3. Extracción de Identificadores
        chat_id = payload.get("chatId") or payload.get("from")
        sender_id = payload.get("from")
        body = payload.get("body")

        # 4. Filtro: Actualizaciones de Estado
        if chat_id == STATUS_BROADCAST_ID or sender_id == STATUS_BROADCAST_ID:
            return {"status": "ignored", "reason": "status_broadcast"}

        # 5. Encolado de Procesamiento
        if chat_id and body:
            logger.info(f"[Webhook] Mensaje válido recibido de {chat_id}. Encolando.")
            background_tasks.add_task(process_message, chat_id, body)
            return {"status": "processing"}
        
        return {"status": "ignored", "reason": "missing_data"}

    except Exception as e:
        logger.error(f"[Webhook] Error al parsear payload: {str(e)}")
        return {"status": "error", "message": str(e)}
