import os
from fastapi import FastAPI
from contextlib import asynccontextmanager
from chainlit.utils import mount_chainlit

# --- CANALES (Channels) ---
from channels.whatsapp.router import router as whatsapp_router
from dotenv import load_dotenv

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic if any
    print("🚀 Server starting...")
    yield
    print("🛑 Server shutting down...")

app = FastAPI(lifespan=lifespan)

# --- 1. Canal WhatsApp (Webhook) ---
app.include_router(whatsapp_router, prefix="/whatsapp")

# --- 2. Health Check ---
@app.get("/health")
async def health_check():
    return {"status": "ok", "architecture": "hybrid-slice"}

# --- 3. Canal UI (Chainlit) ---
# Montamos la UI en la raíz.
# Chainlit tomará el control de "/" y socket.io
# IMPORTANTE: target es relativo al directorio de ejecución (root del repo en docker)
# En docker: WORKDIR /app
# src está en /app/src
# main.py está en /app/src/main.py
mount_chainlit(app=app, target="src/main.py", path="/")
