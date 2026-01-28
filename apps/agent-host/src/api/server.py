"""
Módulo principal del servidor API (Agent Host).

Este módulo inicializa la aplicación FastAPI, gestiona el ciclo de vida de los servicios
(incluyendo la conexión con gateways externos como WhatsApp/WAHA) y configura los
puntos de entrada de la API y la interfaz de usuario.
"""

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

from channels.whatsapp.router import router as whatsapp_router
from core.application.container import Container

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

# Aumentar límite de paquetes para evitar desconexiones en streaming pesado
engineio.payload.Payload.max_decode_packets = 500

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("api.server")

WAHA_BASE_URL = os.getenv("WAHA_BASE_URL", "http://waha:3000")
WAHA_API_KEY = os.getenv("WAHA_API_KEY", "")

DEFAULT_WEBHOOK = "http://agent-host:8000/api/v1/webhooks/whatsapp/webhook"
WEBHOOK_URL = os.getenv("WHATSAPP_WEBHOOK_URL") or DEFAULT_WEBHOOK

WAHA_INIT_TIMEOUT = 60.0
WAHA_POLL_INTERVAL = 2
WAHA_MAX_RETRIES = 15


async def configure_waha_session() -> None:
    """
    Realiza la configuración automática de la sesión de WhatsApp en WAHA.
    """
    session_name = "default"
    headers = {"Content-Type": "application/json", "X-Api-Key": WAHA_API_KEY}
    config_payload = {
        "config": {
            "noweb": {
                "store": {
                    "enabled": True,
                    "fullSync": False
                }
            },
            "webhooks": [{
                "url": WEBHOOK_URL,
                "events": ["message"],
                "retries": {"delaySeconds": 2, "attempts": 5}
            }]
        }
    }

    logger.info(f"[Auto-Config] Esperando a WAHA en: {WAHA_BASE_URL}...")

    # 1. Fase de Polling: Esperar a que el servicio esté online
    service_ready = False
    async with httpx.AsyncClient(timeout=10.0) as client:
        for _ in range(WAHA_MAX_RETRIES):
            try:
                resp = await client.get(f"{WAHA_BASE_URL}/api/server/status", headers=headers)
                if resp.status_code == 200:
                    service_ready = True
                    break
            except Exception:
                pass
            await asyncio.sleep(WAHA_POLL_INTERVAL)

    if not service_ready:
        logger.error("[Auto-Config] WAHA no disponible tras varios reintentos.")
        return

    # 2. Fase de Configuración: Aplicar cambios con un nuevo cliente
    logger.info(f"[Auto-Config] Aplicando configuración a sesión '{session_name}' (esperando 5s para estabilidad)...")
    await asyncio.sleep(5)
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(3):
            try:
                # Intentar actualizar configuración existente
                resp = await client.put(f"{WAHA_BASE_URL}/api/sessions/{session_name}", json=config_payload, headers=headers)
                
                if resp.status_code == 404:
                    logger.info(f"[Auto-Config] Sesión '{session_name}' no encontrada. Creando nueva...")
                    create_payload = config_payload.copy()
                    create_payload["name"] = session_name
                    await client.post(f"{WAHA_BASE_URL}/api/sessions", json=create_payload, headers=headers)
                elif resp.status_code not in [200, 201]:
                    logger.error(f"[Auto-Config] Error al actualizar configuración (Intento {attempt+1}): {resp.text}")
                    continue
                
                # Forzar reinicio para asegurar que el motor (NOWEB) tome el Webhook
                logger.info(f"[Auto-Config] Reiniciando sesión '{session_name}' para aplicar cambios...")
                await client.post(f"{WAHA_BASE_URL}/api/sessions/{session_name}/stop", headers=headers)
                await asyncio.sleep(5) # Más tiempo para NOWEB
                await client.post(f"{WAHA_BASE_URL}/api/sessions/{session_name}/start", headers=headers)
                
                # Verificación final de salud del Webhook
                await asyncio.sleep(2)
                verify = await client.get(f"{WAHA_BASE_URL}/api/sessions/{session_name}", headers=headers)
                if verify.status_code == 200 and verify.json().get("config", {}).get("webhooks"):
                    logger.info(f"✅ [Auto-Config] Sesión '{session_name}' configurada y lista.")
                    return # ÉXITO
                
            except Exception as e:
                logger.warning(f"⚠️ [Auto-Config] Intento {attempt+1} fallido: {e}")
                await asyncio.sleep(5)
        
        logger.error("❌ [Auto-Config] Se agotaron los reintentos de configuración.")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Gestor del ciclo de vida de la aplicación FastAPI.
    
    Maneja la inicialización de tareas en segundo plano y la limpieza de recursos
    al iniciar y detener la aplicación.
    
    Args:
        app (FastAPI): La instancia de la aplicación.
    """
    logger.info("Iniciando servidor API y tareas en segundo plano...")
    asyncio.create_task(configure_waha_session())
    
    yield
    
    logger.info("Apagando servidor API...")
    await Container.cleanup()


app = FastAPI(
    title="SQL Agent OSS API",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(
    whatsapp_router, 
    prefix="/api/v1/webhooks/whatsapp", 
    tags=["Webhooks: WhatsApp"]
)

@app.get("/health", tags=["System"])
async def health_check():
    """Endpoint para verificar el estado de salud del servicio."""
    return {"status": "ok", "service": "agent-host"}

mount_chainlit(app=app, target="src/main.py", path="/")