import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import engineio.payload
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from chainlit.utils import mount_chainlit

# --- 1. CONFIGURACIÓN PRELIMINAR Y PARCHES ---

# Carga robusta de variables de entorno (busca la raíz del proyecto)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

# Parche crítico para EngineIO/SocketIO
# Se aumenta el límite de paquetes para evitar desconexiones durante
# el streaming de respuestas largas o tablas SQL grandes.
# Debe ejecutarse antes de importar cualquier módulo que use websockets.
engineio.payload.Payload.max_decode_packets = 500

# Importación tardía de rutas para asegurar que el entorno esté cargado
from channels.whatsapp.router import router as whatsapp_router
from core.application.container import Container

# --- 2. CONFIGURACIÓN DE LOGGING Y CONSTANTES ---

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("api.server")

# Configuración de WAHA
WAHA_BASE_URL = os.getenv("WAHA_BASE_URL", "http://waha:3000")
WAHA_API_KEY = os.getenv("WAHA_API_KEY", "")

# URL del Webhook: Se prioriza la variable de entorno.
# Si está vacía, se asume la red interna de Docker por defecto.
DEFAULT_WEBHOOK = "http://agent-host:8000/api/v1/webhooks/whatsapp/webhook"
WEBHOOK_URL = os.getenv("WHATSAPP_WEBHOOK_URL") or DEFAULT_WEBHOOK

# Constantes de control
WAHA_INIT_TIMEOUT = 60.0  # Segundos para esperar a que Chrome inicie en WAHA
WAHA_POLL_INTERVAL = 2    # Segundos entre intentos de conexión
WAHA_MAX_RETRIES = 15     # Número máximo de intentos de conexión


async def configure_waha_session() -> None:
    """
    Realiza la configuración automática de la sesión de WhatsApp en WAHA.

    Implementa una estrategia de 'polling' (sondeo) para esperar a que el servicio
    WAHA esté disponible, y posteriormente crea o actualiza la sesión 'default'
    con la configuración del Webhook actual.
    """
    session_name = "default"
    
    # Payload de configuración simplificado para máxima compatibilidad
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
        "Content-Type": "application/json",
        "X-Api-Key": WAHA_API_KEY
    }

    logger.info(f"[Auto-Config] Iniciando configuración. URL Webhook: {WEBHOOK_URL}")
    logger.info(f"[Auto-Config] Buscando servicio WAHA en: {WAHA_BASE_URL}...")

    async with httpx.AsyncClient(timeout=WAHA_INIT_TIMEOUT) as client:
        # 1. Fase de Sondeo (Polling)
        service_ready = False
        for attempt in range(WAHA_MAX_RETRIES):
            try:
                resp = await client.get(f"{WAHA_BASE_URL}/api/server/status", headers=headers)
                
                if resp.status_code == 200:
                    logger.info("[Auto-Config] Servicio WAHA detectado en línea.")
                    service_ready = True
                    break
                elif resp.status_code == 401:
                    logger.error("[Auto-Config] Error de Autenticación (401). Verifique WAHA_API_KEY.")
                    return
            except httpx.RequestError:
                # El servicio aún no responde, continuamos esperando
                pass
            
            await asyncio.sleep(WAHA_POLL_INTERVAL)

        if not service_ready:
            logger.error("[Auto-Config] Tiempo de espera agotado. WAHA no está disponible.")
            return

        # 2. Fase de Configuración (PUT/POST)
        logger.info(f"[Auto-Config] Configurando sesión '{session_name}'...")
        try:
            # Intentamos ACTUALIZAR (PUT) primero
            response = await client.put(
                f"{WAHA_BASE_URL}/api/sessions/{session_name}",
                json=config_payload,
                headers=headers
            )

            if response.status_code == 404:
                # Si no existe, CREAMOS (POST) una nueva
                logger.info(f"[Auto-Config] Sesión no encontrada. Creando nueva sesión...")
                
                # Para POST, el nombre debe ir en el cuerpo del JSON
                create_payload = config_payload.copy()
                create_payload["name"] = session_name
                
                await client.post(
                    f"{WAHA_BASE_URL}/api/sessions",
                    json=create_payload,
                    headers=headers
                )
                logger.info("[Auto-Config] Sesión creada exitosamente.")
            
            elif response.status_code in [200, 201]:
                logger.info("[Auto-Config] Sesión actualizada exitosamente.")
            
            else:
                logger.error(
                    f"[Auto-Config] WAHA rechazó la configuración. "
                    f"Código: {response.status_code}. Razón: {response.text}"
                )

        except Exception as e:
            logger.error(f"[Auto-Config] Error crítico durante la configuración: {str(e)}")


# --- 3. DEFINICIÓN DE LA APLICACIÓN Y LIFESPAN ---

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Gestor del ciclo de vida de la aplicación FastAPI.
    Reemplaza al evento deprecado @app.on_event("startup").
    """
    # Lógica de inicio (Startup)
    logger.info("Iniciando servidor API y tareas en segundo plano...")
    # Ejecutamos la configuración de WAHA como tarea independiente
    asyncio.create_task(configure_waha_session())
    
    yield
    
    # Lógica de cierre (Shutdown)
    logger.info("Apagando servidor API...")
    await Container.cleanup()


app = FastAPI(
    title="SQL Agent OSS API",
    version="1.0.0",
    lifespan=lifespan
)

# --- 4. RUTAS Y MONTAJES ---

# Registro del router de WhatsApp
# Prefijo: /api/v1/webhooks/whatsapp -> Endpoint final: .../webhook
app.include_router(
    whatsapp_router, 
    prefix="/api/v1/webhooks/whatsapp", 
    tags=["Webhooks: WhatsApp"]
)

@app.get("/health", tags=["System"])
async def health_check():
    """Endpoint para verificar el estado de salud del servicio."""
    return {"status": "ok", "service": "agent-host"}

# Montaje de la interfaz de chat (Chainlit)
# Debe ser siempre el último montaje para no interceptar otras rutas API
mount_chainlit(app=app, target="src/main.py", path="/")