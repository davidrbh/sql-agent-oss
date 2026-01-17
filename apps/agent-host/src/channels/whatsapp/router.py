import os
import httpx
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from langchain_core.messages import HumanMessage
from infra.mcp.manager import MCPSessionManager

# Imports de la arquitectura Hybrid Slice
from agent_core.graph import build_graph
from features.sql_analysis.loader import get_sql_tools, get_sql_system_prompt

# Configuración del canal
router = APIRouter(tags=["WhatsApp Channel"])
WAHA_BASE_URL = os.getenv("WAHA_BASE_URL", "http://waha:3000")
WAHA_API_KEY = os.getenv("WAHA_API_KEY")
SIDECAR_URL = os.getenv("SIDECAR_URL", "http://mcp-mysql:3000")

async def process_message(chat_id: str, message_text: str):
    """Procesa un mensaje de WhatsApp en segundo plano.

    Esta función realiza el ciclo completo de vida de una consulta del usuario:
    1. Establece la infraestructura de conexión (MCP Manager).
    2. Carga las "features" del agente (herramientas y prompts).
    3. Construye el grafo del agente.
    4. Invoca el agente con el mensaje del usuario.
    5. Envía la respuesta final de vuelta al usuario a través de la API de WAHA.
    
    Toda la lógica se encapsula en un bloque try/finally para asegurar que
    la conexión MCP se cierre correctamente al finalizar.

    Args:
        chat_id: El ID del chat de WhatsApp del que proviene el mensaje.
        message_text: El contenido del mensaje del usuario.
    """
    mcp_manager = MCPSessionManager(SIDECAR_URL)
    
    try:
        print(f"📩 [WhatsApp Channel] Procesando mensaje de {chat_id}")
        
        # 1. Infraestructura
        await mcp_manager.connect()
        
        # 2. Cargar Feature (SQL Analysis)
        tools = await get_sql_tools(mcp_manager)
        system_prompt = get_sql_system_prompt()
        
        # 3. Construir Cerebro con la feature inyectada
        # TODO: Añadir persistencia real (checkpointer) para mantener hilos por chat_id
        agent = build_graph(tools=tools, system_prompt=system_prompt)
        
        config = {"configurable": {"thread_id": chat_id}}
        inputs = {"messages": [HumanMessage(content=message_text)]}
        
        # 4. Ejecutar
        result = await agent.ainvoke(inputs, config=config)
        bot_response = result["messages"][-1].content
        
        # 5. Responder
        headers = {}
        if WAHA_API_KEY:
            headers["X-Api-Key"] = WAHA_API_KEY

        async with httpx.AsyncClient() as client:
            await client.post(
                f"{WAHA_BASE_URL}/api/sendText",
                json={
                    "chatId": chat_id, 
                    "text": bot_response, 
                    "session": "default"
                },
                headers=headers,
                timeout=10.0
            )
            print(f"✅ [WhatsApp Channel] Respuesta enviada a {chat_id}")

    except Exception as e:
        print(f"❌ [WhatsApp Channel] Error crítico: {e}")
        # Intentar enviar mensaje de error al usuario si es posible
    finally:
        await mcp_manager.close()

@router.post("/webhook")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    """Endpoint para recibir webhooks de WAHA (WhatsApp HTTP API).

    Este es el punto de entrada principal para los mensajes de WhatsApp.
    Valida que el evento sea un mensaje entrante, que no provenga del propio
    agente (para evitar bucles), y delega el procesamiento pesado a una tarea
    en segundo plano (`process_message`) para responder inmediatamente a WAHA.

    Args:
        request: El objeto de la petición FastAPI.
        background_tasks: El gestor de tareas en segundo plano de FastAPI.

    Returns:
        Un diccionario con el estado del procesamiento.
    """
    try:
        data = await request.json()
        
        # 1. Validación de estructura WAHA
        if data.get("event") != "message":
            return {"status": "ignored", "reason": "not_a_message_event"}
            
        payload = data.get("payload", {})
        
        # 2. Evitar bucles infinitos (mensajes propios)
        if payload.get("fromMe"):
            return {"status": "ignored", "reason": "from_me"}
            
        chat_id = payload.get("chatId")
        body = payload.get("body")

        # 3. Encolar tarea
        if chat_id and body:
            background_tasks.add_task(process_message, chat_id, body)
            return {"status": "processing"}
        
        return {"status": "ignored", "reason": "no_content"}

    except Exception as e:
        print(f"❌ [WhatsApp Webhook] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))