import logging
import os
from typing import Dict, Any, Optional

import httpx
from fastapi import APIRouter, Request, BackgroundTasks
from langchain_core.messages import HumanMessage

from infra.mcp.manager import MCPSessionManager
from agent_core.graph import build_graph
from features.sql_analysis.loader import get_sql_tools, get_sql_system_prompt

# Configuración del logger a nivel de módulo
logger = logging.getLogger("uvicorn.error")

router = APIRouter(tags=["Canal WhatsApp"])

# --- Constantes de Configuración ---
WAHA_BASE_URL = os.getenv("WAHA_BASE_URL", "http://waha:3000")
WAHA_API_KEY = os.getenv("WAHA_API_KEY")
SIDECAR_URL = os.getenv("SIDECAR_URL", "http://mcp-mysql:3002")

# ID especial de WhatsApp para actualizaciones de estado (Historias)
STATUS_BROADCAST_ID = "status@broadcast"


async def start_typing(chat_id: str) -> None:
    """
    Envía una señal de 'escribiendo...' al chat de WhatsApp especificado vía WAHA.

    Esta función opera en modo 'fire-and-forget' (disparar y olvidar) para no bloquear
    el flujo principal de ejecución, ya que es una característica cosmética.

    Args:
        chat_id (str): El identificador único del chat de WhatsApp.
    """
    url = f"{WAHA_BASE_URL}/api/startTyping"
    headers = {"Content-Type": "application/json"}
    
    if WAHA_API_KEY:
        headers["X-Api-Key"] = WAHA_API_KEY
    
    payload = {"session": "default", "chatId": chat_id}
    
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload, headers=headers, timeout=2.0)
            logger.info(f"[WhatsApp] Indicador de escritura enviado a {chat_id}")
    except Exception as e:
        # Se loguea como advertencia pero no se lanza excepción, no es crítico.
        logger.warning(f"[WhatsApp] Fallo al enviar indicador de escritura: {str(e)}")


async def send_whatsapp_message(chat_id: str, text: str) -> None:
    """
    Envía un mensaje de texto final al chat de WhatsApp especificado vía WAHA.

    Args:
        chat_id (str): El identificador único del chat de WhatsApp.
        text (str): El contenido del mensaje a enviar.
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
                logger.info(f"[WhatsApp] Mensaje entregado exitosamente a {chat_id}.")
            else:
                logger.error(
                    f"[WhatsApp] Fallo al enviar mensaje. "
                    f"Estado: {response.status_code}, Respuesta: {response.text}"
                )
    except Exception as e:
        logger.error(f"[WhatsApp] Error de conexión al enviar mensaje: {str(e)}")


async def process_message(chat_id: str, message_text: str) -> None:
    """
    Orquesta el flujo de ejecución del agente: conecta a la infraestructura,
    construye el grafo de IA, invoca al agente y envía la respuesta al usuario.

    Args:
        chat_id (str): El identificador único del chat de WhatsApp.
        message_text (str): El mensaje de entrada del usuario.
    """
    mcp_manager = MCPSessionManager(SIDECAR_URL)
    
    try:
        logger.info(f"[WhatsApp] Procesando mensaje de {chat_id}: {message_text[:50]}...")
        
        # 1. Feedback Visual (UX)
        await start_typing(chat_id)

        # 2. Configuración de Infraestructura
        await mcp_manager.connect()
        
        # 3. Inicialización del Agente
        tools = await get_sql_tools(mcp_manager)
        system_prompt = get_sql_system_prompt()
        agent = build_graph(tools=tools, system_prompt=system_prompt)
        
        # Configuración para LangGraph
        # 'recursion_limit' se aumenta a 50 para manejar bucles de corrección SQL complejos.
        config = {
            "configurable": {"thread_id": chat_id},
            "recursion_limit": 50
        }
        
        inputs = {"messages": [HumanMessage(content=message_text)]}
        
        # 4. Ejecución del Agente
        logger.info("[WhatsApp] Invocando Agente de IA...")
        result = await agent.ainvoke(inputs, config=config)
        
        bot_response = result["messages"][-1].content
        
        # 5. Entrega de Respuesta
        await send_whatsapp_message(chat_id, bot_response)

    except Exception as e:
        logger.error(f"[WhatsApp] Error crítico durante el procesamiento: {str(e)}")
        # Mensaje de respaldo al usuario en caso de error técnico
        error_message = (
            "Lo siento, ocurrió un error interno al procesar tu solicitud. "
            "Por favor, intenta nuevamente más tarde."
        )
        await send_whatsapp_message(chat_id, error_message)
    finally:
        # Asegurar cierre de conexiones
        await mcp_manager.close()


@router.post("/webhook")
async def whatsapp_webhook(
    request: Request, 
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    Endpoint para recibir webhooks del servicio WAHA.

    Valida el payload entrante, filtra eventos irrelevantes (como actualizaciones
    de estado o mensajes propios) y encola los mensajes válidos para su procesamiento
    en segundo plano.

    Args:
        request (Request): La solicitud HTTP entrante con el payload JSON.
        background_tasks (BackgroundTasks): Utilidad de FastAPI para tareas asíncronas.

    Returns:
        Dict[str, Any]: Un diccionario de estado indicando el resultado del procesamiento.
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
        # WAHA puede enviar 'chatId' o 'from' dependiendo del contexto
        chat_id = payload.get("chatId") or payload.get("from")
        sender_id = payload.get("from")
        body = payload.get("body")

        # 4. Filtro: Actualizaciones de Estado (Historias)
        # Es CRÍTICO ignorar 'status@broadcast' para no responder a historias públicas.
        if chat_id == STATUS_BROADCAST_ID or sender_id == STATUS_BROADCAST_ID:
            logger.info("[Webhook] Actualización de estado (broadcast) ignorada.")
            return {"status": "ignored", "reason": "status_broadcast"}

        # 5. Encolado de Procesamiento
        if chat_id and body:
            logger.info(f"[Webhook] Mensaje válido recibido de {chat_id}. Encolando tarea.")
            # Se usa background_tasks para responder 200 OK inmediatamente a WAHA
            background_tasks.add_task(process_message, chat_id, body)
            return {"status": "processing"}
        
        return {"status": "ignored", "reason": "missing_data"}

    except Exception as e:
        logger.error(f"[Webhook] Error al parsear payload del webhook: {str(e)}")
        return {"status": "error", "message": str(e)}