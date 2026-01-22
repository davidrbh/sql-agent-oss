import os
import logging
import asyncio
from dotenv import load_dotenv
from telegram import Update, constants
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# --- IMPORTAMOS EL CEREBRO UNIFICADO ---
from langchain_core.messages import HumanMessage
# Asegúrate de que estas rutas existan en tu agent_core
from agent_core.graph import build_graph 
from agent_core.main import build_context 

# Cargar variables de entorno
load_dotenv()

# Configuración de Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- ESTADO GLOBAL ---
global_graph = None
user_histories = {} 

async def initialize_agent():
    """
    Construye el grafo completo con LÓGICA DE REINTENTO.
    Esto es vital para esperar a que el Sidecar (MySQL) esté listo.
    """
    global global_graph
    
    if global_graph:
        return global_graph

    max_retries = 15
    retry_delay = 5 # segundos

    logger.info("🔌 [Telegram] Iniciando secuencia de conexión con el Cerebro...")

    for attempt in range(max_retries):
        try:
            # 1. Construimos el contexto (Esto intenta conectar al MCP Sidecar)
            # Si el sidecar no está listo, esto lanzará una excepción
            context = await build_context()
            
            # 2. Construimos el grafo
            # Usamos unpacking (**) asumiendo que build_context retorna {'tools': ..., 'system_prompt': ...}
            global_graph = build_graph(**context)
            
            logger.info("🧠 [Telegram] Agente CONECTADO y LISTO (Clasificador + SQL + API).")
            return global_graph

        except Exception as e:
            logger.warning(f"⏳ [Telegram] Intento {attempt + 1}/{max_retries} fallido. El Sidecar/API no responde aún.")
            logger.warning(f"   Razón: {str(e)}")
            
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                logger.error("❌ [Telegram] Se agotaron los reintentos. Error fatal.")
                raise e

async def send_long_message(update: Update, text: str):
    """
    Rompe mensajes largos en trozos compatibles con Telegram (4096 chars).
    """
    MAX_LENGTH = 4000 
    
    if len(text) <= MAX_LENGTH:
        try:
            await update.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN)
        except Exception:
            # Fallback si el Markdown está roto (común en LLMs que cierran mal tags)
            await update.message.reply_text(text)
        return

    # Si es largo, lo partimos
    for i in range(0, len(text), MAX_LENGTH):
        chunk = text[i:i + MAX_LENGTH]
        try:
            await update.message.reply_text(chunk)
        except Exception as e:
            logger.error(f"Error enviando chunk: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Hola, soy tu Agente IA**\n\n"
        "Estoy conectado al sistema central.\n"
        "Puedo consultar la base de datos y APIs externas.\n\n"
        "¿En qué te ayudo hoy?",
        parse_mode=constants.ParseMode.MARKDOWN
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    
    # UX: "Escribiendo..."
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)

    # 1. Lazy Init (Por seguridad, aunque post_init debería haberlo hecho)
    if not global_graph:
        try:
            await initialize_agent()
        except Exception:
            await update.message.reply_text("⚠️ El sistema se está iniciando, intenta en unos segundos...")
            return

    # 2. Historial (Memoria volátil en RAM)
    if chat_id not in user_histories:
        user_histories[chat_id] = []
    
    history = user_histories[chat_id]
    history.append(HumanMessage(content=user_text))

    logger.info(f"📩 [Chat {chat_id}] Procesando: {user_text[:50]}...")

    try:
        inputs = {"messages": history}
        
        # 3. Invocación al Grafo
        response = await global_graph.ainvoke(inputs)
        
        # 4. Procesar respuesta
        final_messages = response.get("messages", [])
        if final_messages:
            last_msg = final_messages[-1]
            ai_content = last_msg.content
            
            # Actualizamos historial local
            user_histories[chat_id] = final_messages
            
            # 5. Enviar respuesta
            await send_long_message(update, ai_content)
        else:
            await update.message.reply_text("🤔 El agente procesó la solicitud pero no generó respuesta de texto.")

    except Exception as e:
        logger.error(f"❌ Error procesando mensaje: {str(e)}")
        await update.message.reply_text("⚠️ Ocurrió un error interno procesando tu solicitud.")

async def post_init(application: ApplicationBuilder):
    """
    Se ejecuta justo antes de empezar a escuchar mensajes.
    Ideal para esperar a que el Sidecar esté listo.
    """
    await initialize_agent()

if __name__ == '__main__':
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("❌ Falta TELEGRAM_BOT_TOKEN en .env")
        exit(1)

    logger.info("🚀 Iniciando Telegram Bot...")
    
    # post_init asegura que conectemos antes de aceptar mensajes
    application = ApplicationBuilder().token(token).post_init(post_init).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    logger.info("📡 Escuchando mensajes...")
    application.run_polling()