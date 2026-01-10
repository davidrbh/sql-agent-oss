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
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://evolution_api:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
AGENT_API_KEY = os.getenv("AGENT_API_KEY", "secret_agent_key") # Para proteger nuestro webhook

# Inicializar App y Grafo
app = FastAPI(title="WhatsApp Bridge for SQL Agent")
agent_graph = build_graph()

# Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whatsapp_bridge")

class WebhookPayload(BaseModel):
    event: str
    instance: str
    data: Dict[str, Any]
    sender: str
    apikey: Optional[str] = None

@app.get("/health")
def health_check():
    return {"status": "ok", "agent": "connected"}

@app.post("/webhook")
async def receive_message(request: Request, secret: Optional[str] = Query(None)):
    """
    Webhook que recibe eventos de Evolution API (Typebot/Wpp).
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

    # 1. Validación Básica (Opcional, filtrar por eventos)
    event_type = payload.get("event")
    if event_type != "messages.upsert":
        return {"status": "ignored", "reason": "Not a message event"}

    data = payload.get("data", {})
    key = data.get("key", {})
    
    # Ignorar mensajes propios (fromMe)
    if key.get("fromMe", False):
        return {"status": "ignored", "reason": "Self message"}

    # 2. Extraer información
    remote_jid = key.get("remoteJid") # ID del chat (ej: 573001234567@s.whatsapp.net)
    push_name = data.get("pushName", "User")
    
    # Extraer texto (soporta Texto simple y Extendido)
    message_content = data.get("message", {})
    user_text = (
        message_content.get("conversation") or 
        message_content.get("extendedTextMessage", {}).get("text") or
        ""
    )

    if not user_text:
        return {"status": "ignored", "reason": "No text content"}

    logger.info(f"📩 Mensaje de {push_name} ({remote_jid}): {user_text}")

    # 3. Invocar al Agente SQL
    # Nota: Aquí no mantenemos historial persistente por sesión compleja en este MVP,
    # pero podríamos usar Redis o memoria en el futuro.
    # Por ahora, enviamos solo el mensaje actual (Stateless) o un historial corto.
    
    try:
        inputs = {
            "question": user_text,
            "messages": [HumanMessage(content=user_text)] 
            # En v2.2 podríamos cargar historial de DB usando remote_jid
        }
        
        result = await agent_graph.ainvoke(inputs)
        ai_response = result["messages"][-1].content
        
        # 4. Enviar respuesta a WhatsApp
        await send_whatsapp_message(remote_jid, ai_response, payload.get("instance"))
        
    except Exception as e:
        logger.error(f"❌ Error procesando mensaje: {e}")
        # Opcional: Enviar mensaje de error al usuario
        await send_whatsapp_message(remote_jid, "⚠️ Ocurrió un error interno consultando mis datos.", payload.get("instance"))

    return {"status": "processed"}

async def send_whatsapp_message(remote_jid: str, text: str, instance: str):
    """Envía mensaje de vuelta usando Evolution API"""
    url = f"{EVOLUTION_API_URL}/message/sendText/{instance}"
    
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }
    
    body = {
        "number": remote_jid,
        # "options": {"delay": 1200, "presence": "composing"}, # Simular escritura
        "text": text
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=body, headers=headers) as resp:
            if resp.status != 201 and resp.status != 200:
                logger.error(f"⚠️ Fallo al enviar WhatsApp: {await resp.text()}")
            else:
                logger.info(f"📤 Respuesta enviada a {remote_jid}")
