import os
import logging
import aiohttp
from fastapi import FastAPI, Request, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional

# Importar el Singleton del Agente
from sql_agent.graph import build_graph
from langchain_core.messages import HumanMessage

# Configuración
WAHA_BASE_URL = os.getenv("WAHA_BASE_URL", "http://waha:3000")
WAHA_API_KEY = os.getenv("WAHA_API_KEY", "")
AGENT_API_KEY = os.getenv("AGENT_API_KEY", "secret_agent_key") # Para proteger nuestro webhook

# Inicializar App y Grafo
app = FastAPI(title="WhatsApp Bridge for SQL Agent (WAHA)")
agent_graph = build_graph()

# Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whatsapp_bridge")

@app.get("/health")
def health_check():
    return {"status": "ok", "agent": "connected", "platform": "waha"}

@app.post("/webhook")
async def receive_message(request: Request, secret: Optional[str] = Query(None)):
    """
    Webhook que recibe eventos de WAHA (WhatsApp HTTP API).
    Requiere ?secret=AGENT_API_KEY para seguridad.
    """
    # 0. Seguridad: Verificar Token
    if secret != AGENT_API_KEY:
        logger.warning(f"⛔ Intento de acceso no autorizado. Secret recibido: {secret}")
        raise HTTPException(status_code=403, detail="Forbidden: Invalid Secret")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # 1. Validación Básica
    # WAHA envía { "event": "message", "session": "default", "payload": { ... } }
    event_type = payload.get("event")
    
    # Solo procesamos mensajes de texto entrantes
    if event_type != "message":
        return {"status": "ignored", "reason": f"Event {event_type} not supported"}

    data = payload.get("payload", {})
    
    # Ignorar mensajes propios (fromMe)
    if data.get("fromMe", False):
        return {"status": "ignored", "reason": "Self message"}
    
    # Ignorar mensajes de estado o grupos (opcional)
    # if "@g.us" in data.get("from", ""):
    #      return {"status": "ignored", "reason": "Group message"}

    # 2. Extraer información
    remote_jid = data.get("from") # ID del chat (ej: 573001234567@c.us)
    push_name = data.get("_data", {}).get("notifyName", "User")
    
    # Extraer texto
    user_text = data.get("body", "")

    if not user_text:
        return {"status": "ignored", "reason": "No text content"}

    logger.info(f"📩 Mensaje de {push_name} ({remote_jid}): {user_text}")

    # 3. Invocar al Agente SQL
    try:
        inputs = {
            "question": user_text,
            "messages": [HumanMessage(content=user_text)] 
        }
        
        result = await agent_graph.ainvoke(inputs)
        ai_response = result["messages"][-1].content
        
        # 4. Enviar respuesta a WhatsApp via WAHA
        session_name = payload.get("session", "default")
        await send_whatsapp_message(remote_jid, ai_response, session_name)
        
    except Exception as e:
        logger.error(f"❌ Error procesando mensaje: {e}")
        # Opcional: Enviar mensaje de error al usuario
        # await send_whatsapp_message(remote_jid, "⚠️ Error interno.", payload.get("session", "default"))

    return {"status": "processed"}

async def send_whatsapp_message(chat_id: str, text: str, session: str):
    """Envía mensaje de vuelta usando WAHA"""
    url = f"{WAHA_BASE_URL}/api/sendText"
    
    headers = {
        "X-Api-Key": WAHA_API_KEY,
        "Content-Type": "application/json"
    }
    
    body = {
        "chatId": chat_id,
        "text": text,
        "session": session
    }
    
    async with aiohttp.ClientSession() as session_http:
        async with session_http.post(url, json=body, headers=headers) as resp:
            if resp.status != 201 and resp.status != 200:
                error_text = await resp.text()
                logger.error(f"⚠️ Fallo al enviar WhatsApp: {resp.status} - {error_text}")
            else:
                logger.info(f"📤 Respuesta enviada a {chat_id}")

