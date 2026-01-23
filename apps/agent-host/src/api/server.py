import os
import asyncio
import httpx
import logging
from dotenv import load_dotenv
load_dotenv()
# 👇 1. SOLUCIÓN CRÍTICA "Too many packets in payload"
# Esto debe ir ANTES de importar FastAPI o Chainlit para evitar desconexiones
# cuando el agente envía respuestas largas o tablas SQL.
import engineio.payload
engineio.payload.Payload.max_decode_packets = 500

from fastapi import FastAPI
from chainlit.utils import mount_chainlit


# --- CANALES (Channels) ---
from channels.whatsapp.router import router as whatsapp_router



# --- 2. CONFIGURACIÓN DE LOGS ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn.error")

# --- 3. CONFIGURACIÓN DE ENTORNOS ---
# Usamos puerto 3000 para hablar con WAHA internamente en Docker
WAHA_BASE_URL = os.getenv("WAHA_BASE_URL", "http://waha:3000")
WAHA_API_KEY = os.getenv("WAHA_API_KEY", "")

# Esta URL debe coincidir con el prefix de abajo + /webhook del router
# ✅ BIEN: El "or" obliga a usar el default si la variable es None o "" (vacía)
WEBHOOK_URL = os.getenv("WHATSAPP_WEBHOOK_URL") 

# 👇 Agrega este print temporalmente para ver qué está pasando realmente
logger.info(f"🔍 [Debug] URL del Webhook que se enviará: '{WEBHOOK_URL}'")

async def configure_waha_session():
    """Configura la sesión de WAHA con reintentos y timeout extendido."""
    session_name = "default"
    
    # Payload simplificado
    config_payload = {
        "config": {
            "webhooks": [{
                "url": WEBHOOK_URL,
                "events": ["message"],
                "retries": {
                    "delaySeconds": 2,
                    "attempts": 5
                }
            }]
        }
    }

    headers = {
        "X-Api-Key": WAHA_API_KEY,
        "Content-Type": "application/json"
    }

    logger.info(f"⏳ [Auto-Config] Buscando WAHA en: {WAHA_BASE_URL}...")
    
    # 👇 FIX: Timeout de 60 segundos para dar tiempo a que Chrome arranque
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Bucle de espera (Polling)
        max_retries = 15
        for i in range(max_retries):
            try:
                resp = await client.get(f"{WAHA_BASE_URL}/api/server/status", headers=headers)
                
                if resp.status_code == 200:
                    logger.info("✅ WAHA detectado online.")
                    break
                elif resp.status_code == 401:
                    logger.error("❌ Error de Auth (401). Revisa tu WAHA_API_KEY.")
                    return
            except httpx.RequestError:
                pass 
            
            if i == max_retries - 1:
                logger.error("⚠️ [Auto-Config] WAHA no respondió. Abortando.")
                return
            await asyncio.sleep(2)

        # Inyectar Configuración
        logger.info(f"⚙️ [Auto-Config] Configurando sesión '{session_name}'...")
        try:
            # PUT (Actualizar)
            response = await client.put(
                f"{WAHA_BASE_URL}/api/sessions/{session_name}",
                json=config_payload, headers=headers
            )

            if response.status_code == 404:
                # POST (Crear)
                create_payload = config_payload.copy()
                create_payload["name"] = session_name
                
                logger.info(f"🆕 Creando nueva sesión...")
                await client.post(
                    f"{WAHA_BASE_URL}/api/sessions",
                    json=create_payload, headers=headers
                )
                logger.info("✅ [Auto-Config] Sesión CREADA.")
            elif response.status_code in [200, 201]:
                logger.info("✅ [Auto-Config] Sesión ACTUALIZADA.")
            else:
                logger.error(f"❌ [Auto-Config] WAHA rechazó la config: {response.status_code} - {response.text}")

        except Exception as e:
            # 👇 FIX DE LOGS: Imprimimos el TIPO de error para saber si es Timeout
            logger.error(f"❌ [Auto-Config] Error crítico ({type(e).__name__}): {e}")

# --- DEFINICIÓN DE LA APP ---
app = FastAPI(title="SQL Agent OSS API", version="1.0.0")

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Server starting (Event Hook)...")
    asyncio.create_task(configure_waha_session())

# --- RUTAS ---
# Aquí definimos el prefijo base.
# Como en router.py es @router.post("/webhook"), la URL final es:
# /api/v1/webhooks/whatsapp/webhook
app.include_router(
    whatsapp_router, 
    prefix="/api/v1/webhooks/whatsapp", 
    tags=["Webhooks: WhatsApp"]
)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Montar Chainlit al final
mount_chainlit(app=app, target="src/main.py", path="/")
