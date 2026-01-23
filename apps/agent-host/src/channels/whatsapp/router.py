import os
import httpx
import logging
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from langchain_core.messages import HumanMessage
from infra.mcp.manager import MCPSessionManager
from agent_core.graph import build_graph
from features.sql_analysis.loader import get_sql_tools, get_sql_system_prompt

logger = logging.getLogger("uvicorn.error")
router = APIRouter(tags=["WhatsApp Channel"])

WAHA_BASE_URL = os.getenv("WAHA_BASE_URL", "http://waha:3000")
WAHA_API_KEY = os.getenv("WAHA_API_KEY")
SIDECAR_URL = os.getenv("SIDECAR_URL", "http://mcp-mysql:3002")

# --- 🆕 FUNCIÓN NUEVA: INDICADOR DE ESCRIBIENDO ---
async def start_typing(chat_id: str):
    """Envía la señal de 'Escribiendo...' a WhatsApp"""
    url = f"{WAHA_BASE_URL}/api/startTyping"
    headers = {"Content-Type": "application/json"}
    if WAHA_API_KEY:
        headers["X-Api-Key"] = WAHA_API_KEY
    
    payload = {"session": "default", "chatId": chat_id}
    
    try:
        async with httpx.AsyncClient() as client:
            # No esperamos respuesta (fire and forget) para no bloquear
            await client.post(url, json=payload, headers=headers, timeout=2.0)
            logger.info(f"✍️ [WhatsApp] 'Escribiendo...' enviado a {chat_id}")
    except Exception as e:
        logger.warning(f"⚠️ No se pudo enviar estado 'Escribiendo': {e}")

async def send_whatsapp_message(chat_id: str, text: str):
    """Envía el mensaje final y detiene el typing automáticamente"""
    headers = {"Content-Type": "application/json"}
    if WAHA_API_KEY:
        headers["X-Api-Key"] = WAHA_API_KEY

    payload = {"chatId": chat_id, "text": text, "session": "default"}

    try:
        async with httpx.AsyncClient() as client:
            logger.info(f"📤 [WhatsApp] Enviando respuesta...")
            response = await client.post(
                f"{WAHA_BASE_URL}/api/sendText",
                json=payload,
                headers=headers,
                timeout=20.0
            )
            if response.status_code in [200, 201]:
                logger.info(f"✅ [WhatsApp] Mensaje entregado.")
            else:
                logger.error(f"⚠️ [WhatsApp] Fallo envío: {response.text}")
    except Exception as e:
        logger.error(f"❌ [WhatsApp] Error conexión: {e}")

async def process_message(chat_id: str, message_text: str):
    mcp_manager = MCPSessionManager(SIDECAR_URL)
    
    try:
        logger.info(f"📩 [WhatsApp] Procesando: {message_text[:30]}...")
        
        # 1. 🆕 EFECTO VISUAL: Activar "Escribiendo..."
        # Lo ponemos al principio para que el usuario vea feedback inmediato
        await start_typing(chat_id)

        # 2. Infraestructura
        await mcp_manager.connect()
        
        # 3. Construir Cerebro
        tools = await get_sql_tools(mcp_manager)
        system_prompt = get_sql_system_prompt()
        agent = build_graph(tools=tools, system_prompt=system_prompt)
        
        config = {"configurable": {"thread_id": chat_id}}
        inputs = {"messages": [HumanMessage(content=message_text)]}
        
        # 4. Invocando AI (Aquí es donde el usuario espera)
        logger.info("🧠 [WhatsApp] Agente pensando...")
        result = await agent.ainvoke(inputs, config=config)
        bot_response = result["messages"][-1].content
        
        # 5. Responder (WAHA detiene el 'typing' automáticamente al enviar texto)
        await send_whatsapp_message(chat_id, bot_response)

    except Exception as e:
        logger.error(f"❌ [WhatsApp] Error: {e}")
        await send_whatsapp_message(chat_id, "⚠️ Ocurrió un error interno.")
    finally:
        await mcp_manager.close()

@router.post("/webhook")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
        
        if data.get("event") != "message":
            return {"status": "ignored"}
            
        payload = data.get("payload", {})
        
        if payload.get("fromMe"):
            return {"status": "ignored"}
            
        chat_id = payload.get("chatId") or payload.get("from")
        body = payload.get("body")

        if chat_id and body:
            logger.info(f"✅ [Webhook] Mensaje de {chat_id}. Procesando...")
            background_tasks.add_task(process_message, chat_id, body)
            return {"status": "processing"}
        
        return {"status": "ignored"}

    except Exception as e:
        logger.error(f"❌ [Webhook] Error: {e}")
        return {"status": "error"}