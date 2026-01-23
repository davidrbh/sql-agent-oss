import os
import httpx
import logging
from fastapi import APIRouter, Request, BackgroundTasks
from langchain_core.messages import HumanMessage
from infra.mcp.manager import MCPSessionManager
from agent_core.graph import build_graph
from features.sql_analysis.loader import get_sql_tools, get_sql_system_prompt

# --- Configuración de Logs (Visible en Docker) ---
logger = logging.getLogger("uvicorn.error")

router = APIRouter(tags=["WhatsApp Channel"])

# --- Configuración de Entorno ---
# Default puerto 3000 (WAHA interno) y 3002 (MCP interno)
WAHA_BASE_URL = os.getenv("WAHA_BASE_URL", "http://waha:3000")
WAHA_API_KEY = os.getenv("WAHA_API_KEY")
SIDECAR_URL = os.getenv("SIDECAR_URL", "http://mcp-mysql:3002")

# --- FUNCIONES AUXILIARES ---

async def start_typing(chat_id: str):
    """Envía efecto 'Escribiendo...' (Fire and Forget)"""
    url = f"{WAHA_BASE_URL}/api/startTyping"
    headers = {"Content-Type": "application/json"}
    if WAHA_API_KEY:
        headers["X-Api-Key"] = WAHA_API_KEY
    
    payload = {"session": "default", "chatId": chat_id}
    
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload, headers=headers, timeout=2.0)
            logger.info(f"✍️ [WhatsApp] 'Escribiendo...' enviado a {chat_id}")
    except Exception:
        # No bloqueamos si falla el typing, es cosmético
        pass

async def send_whatsapp_message(chat_id: str, text: str):
    """Envía el mensaje de texto final a WAHA"""
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
                logger.info(f"✅ [WhatsApp] Mensaje entregado correctamente.")
            else:
                logger.error(f"⚠️ [WhatsApp] Error WAHA: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"❌ [WhatsApp] Error de conexión: {e}")

# --- LÓGICA PRINCIPAL DEL AGENTE ---

async def process_message(chat_id: str, message_text: str):
    mcp_manager = MCPSessionManager(SIDECAR_URL)
    
    try:
        logger.info(f"📩 [WhatsApp] Procesando mensaje: {message_text[:30]}...")
        
        # 1. Feedback visual
        await start_typing(chat_id)

        # 2. Infraestructura
        await mcp_manager.connect()
        
        # 3. Construir Cerebro
        tools = await get_sql_tools(mcp_manager)
        system_prompt = get_sql_system_prompt()
        agent = build_graph(tools=tools, system_prompt=system_prompt)
        
        # 👇 CONFIGURACIÓN CRÍTICA: Límite de recursión
        config = {
            "configurable": {"thread_id": chat_id},
            "recursion_limit": 50  # 🚀 Evita el error "limit of 25 reached"
        }
        
        inputs = {"messages": [HumanMessage(content=message_text)]}
        
        # 4. Invocando AI
        logger.info("🧠 [WhatsApp] Agente pensando...")
        result = await agent.ainvoke(inputs, config=config)
        
        bot_response = result["messages"][-1].content
        
        # 5. Responder
        await send_whatsapp_message(chat_id, bot_response)

    except Exception as e:
        logger.error(f"❌ [WhatsApp] Error Agente: {e}")
        await send_whatsapp_message(chat_id, "⚠️ Lo siento, ocurrió un error técnico interno procesando tu solicitud.")
    finally:
        await mcp_manager.close()

# --- ENDPOINT WEBHOOK ---

@router.post("/webhook")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
        
        # Validaciones básicas
        if data.get("event") != "message":
            return {"status": "ignored"}
            
        payload = data.get("payload", {})
        
        # Ignorar mensajes propios
        if payload.get("fromMe"):
            return {"status": "ignored"}
            
        # Obtener ID (Soporta ambos formatos de WAHA)
        chat_id = payload.get("chatId") or payload.get("from")
        body = payload.get("body")

        if chat_id and body:
            logger.info(f"✅ [Webhook] Mensaje recibido de {chat_id}. Encolando...")
            # Procesar en segundo plano para responder rápido a WAHA
            background_tasks.add_task(process_message, chat_id, body)
            return {"status": "processing"}
        
        return {"status": "ignored", "reason": "no_data"}

    except Exception as e:
        logger.error(f"❌ [Webhook] Excepción: {e}")
        return {"status": "error"}