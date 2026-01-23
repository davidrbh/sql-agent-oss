import os
import asyncio
import httpx
import logging
from fastapi import FastAPI
from chainlit.utils import mount_chainlit
from dotenv import load_dotenv

# --- CANALES (Channels) ---
from channels.whatsapp.router import router as whatsapp_router

load_dotenv()

# --- 1. CONFIGURACIÓN DE LOGS ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn.error")

# --- CONFIGURACIÓN DE WAHA ---
# ⚠️ CAMBIO CLAVE: Usamos puerto 3000 (interno de Docker), no 3001
WAHA_BASE_URL = os.getenv("WAHA_BASE_URL", "http://waha:3000")
WAHA_API_KEY = os.getenv("WAHA_API_KEY", "")
WEBHOOK_URL = os.getenv("WHATSAPP_WEBHOOK_URL", "http://agent-host:8000/api/v1/webhooks/whatsapp/webhook")

async def configure_waha_session():
    """Configura la sesión de WAHA con reintentos."""
    session_name = "default"
    config_payload = {
        "name": session_name,
        "config": {
            "webhooks": [{
                "url": WEBHOOK_URL,
                "events": ["message"],
                "retries": {
                    "delaySeconds": 2,
                    "attempts": 5,
                    "policy": "linear"
                }
            }]
        }
    }

    # 👇 DEFINIMOS HEADERS ANTES DEL BUCLE (Para usarlos en el Health Check)
    headers = {
        "X-Api-Key": WAHA_API_KEY,
        "Content-Type": "application/json"
    }

    logger.info(f"⏳ [Auto-Config] Buscando WAHA en: {WAHA_BASE_URL}...")
    
    async with httpx.AsyncClient() as client:
        # 1. Bucle de espera (Polling)
        max_retries = 15
        for i in range(max_retries):
            try:
                # 👇 AQUI ESTABA EL ERROR 401: Faltaba pasar 'headers=headers'
                resp = await client.get(
                    f"{WAHA_BASE_URL}/api/server/status", 
                    headers=headers
                )
                
                if resp.status_code == 200:
                    logger.info("✅ WAHA detectado online.")
                    break
                elif resp.status_code == 401:
                    logger.error("❌ Error de Auth (401). Revisa tu WAHA_API_KEY en el .env")
                    return
            except httpx.RequestError:
                pass 
            
            if i == max_retries - 1:
                logger.error("⚠️ [Auto-Config] WAHA no respondió. Abortando.")
                return

            await asyncio.sleep(2)

        # 2. Inyectar Configuración
        logger.info(f"⚙️ [Auto-Config] Configurando sesión '{session_name}'...")

        try:
            # PUT (Actualizar)
            response = await client.put(
                f"{WAHA_BASE_URL}/api/sessions/{session_name}",
                json=config_payload,
                headers=headers
            )

            if response.status_code == 404:
                # POST (Crear)
                logger.info(f"🆕 La sesión no existe. Creando nueva...")
                await client.post(
                    f"{WAHA_BASE_URL}/api/sessions",
                    json=config_payload,
                    headers=headers
                )
                logger.info("✅ [Auto-Config] Sesión CREADA exitosamente.")
            elif response.status_code in [200, 201]:
                logger.info("✅ [Auto-Config] Sesión ACTUALIZADA exitosamente.")
            else:
                logger.warning(f"⚠️ [Auto-Config] Respuesta inesperada: {response.status_code}")

        except Exception as e:
            logger.error(f"❌ [Auto-Config] Error crítico: {e}")

# --- DEFINICIÓN DE LA APP ---
app = FastAPI(
    title="SQL Agent OSS API",
    version="1.0.0"
)

# --- 2. EVENTO DE INICIO ---
@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Server starting (Event Hook)...")
    asyncio.create_task(configure_waha_session())

# --- RUTAS ---
app.include_router(
    whatsapp_router, 
    prefix="/api/v1/webhooks/whatsapp", 
    tags=["Webhooks: WhatsApp"]
)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

mount_chainlit(app=app, target="src/main.py", path="/")
