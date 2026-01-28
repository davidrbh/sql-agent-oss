"""
Punto de entrada para el canal de comunicación de Telegram.

Este módulo gestiona la interacción con el bot de Telegram, incluyendo la
inicialización del agente de IA, el manejo de mensajes entrantes y la
gestión del historial de conversación por usuario.
"""

import os
import logging
import asyncio
from dotenv import load_dotenv
from telegram import Update, constants
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from langchain_core.messages import HumanMessage

from core.application.workflows.graph import build_graph 
from core.application.container import Container
from features.sql_analysis.loader import get_sql_system_prompt

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

global_graph = None
user_histories = {}


async def initialize_agent():
    """
    Construye el grafo del agente con lógica de reintento.

    Intenta conectar con la infraestructura necesaria (MCP Sidecars) y 
    configura el motor de razonamiento. Reintenta en caso de que los 
    servicios dependientes no estén listos.

    Returns:
        StateGraph: La instancia del grafo compilado del agente.
    """
    global global_graph
    
    if global_graph:
        return global_graph

    max_retries = 15
    retry_delay = 5

    logger.info("Iniciando secuencia de conexión con el núcleo cognitivo...")

    for attempt in range(max_retries):
        try:
            tool_provider = Container.get_tool_provider()
            tools = await tool_provider.get_tools()
            system_prompt = get_sql_system_prompt(channel="telegram")

            # Inyectamos None en checkpointer para usar memoria volátil en RAM para Telegram
            # TODO: Migrar a persistencia PostgreSQL mediante thread_id de Telegram
            global_graph = build_graph(tools, system_prompt, checkpointer=None)
            
            logger.info("Agente conectado y listo (Clasificador + SQL + API).")
            return global_graph

        except Exception as e:
            logger.warning(f"Intento {attempt + 1}/{max_retries} fallido. Reintentando en {retry_delay}s...")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
            else:
                logger.error("Se agotaron los reintentos de conexión.")
                raise e


async def send_long_message(update: Update, text: str):
    """
    Envía mensajes dividiéndolos si superan el límite de Telegram.

    Args:
        update (Update): El objeto de actualización de Telegram.
        text (str): El contenido del mensaje a enviar.
    """
    max_length = 4000 
    
    if len(text) <= max_length:
        try:
            await update.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN)
        except Exception:
            await update.message.reply_text(text)
        return

    for i in range(0, len(text), max_length):
        chunk = text[i:i + max_length]
        try:
            await update.message.reply_text(chunk)
        except Exception as e:
            logger.error(f"Error enviando fragmento de mensaje: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Manejador del comando /start.
    """
    await update.message.reply_text(
        "\U0001F64B **Hola, soy tu Agente IA**\n\n"
        "Estoy conectado al sistema central.\n"
        "Puedo consultar la base de datos y APIs externas.\n\n"
        "\u00BFEn qué te ayudo hoy?",
        parse_mode=constants.ParseMode.MARKDOWN
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Procesa los mensajes de texto entrantes de los usuarios.
    """
    global global_graph
    chat_id = update.effective_chat.id
    user_text = update.message.text
    
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)

    # 1. Asegurar que el agente esté inicializado
    if not global_graph:
        try:
            await initialize_agent()
        except Exception:
            await update.message.reply_text("⚠️ El sistema se está iniciando, intenta en unos segundos...")
            return

    if chat_id not in user_histories:
        user_histories[chat_id] = []
    
    history = user_histories[chat_id]
    history.append(HumanMessage(content=user_text))

    logger.info(f"Procesando mensaje de chat {chat_id}")

    try:
        inputs = {"messages": history}
        response = await global_graph.ainvoke(inputs)
        
        final_messages = response.get("messages", [])
        if final_messages:
            last_msg = final_messages[-1]
            user_histories[chat_id] = final_messages
            
            # 2. Detección de auto-reparación (Self-Healing)
            # Si el agente detecta internamente que la conexión se rompió, 
            # forzamos la re-inicialización del grafo para el siguiente mensaje.
            if "reiniciado el túnel de datos" in last_msg.content:
                logger.warning("🔴 Detectada señal de auto-reparación. Reseteando grafo global de Telegram.")
                global_graph = None
                
            await send_long_message(update, last_msg.content)
        else:
            await update.message.reply_text("El agente no generó una respuesta de texto.")

    except Exception as e:
        logger.error(f"Error procesando mensaje de Telegram: {str(e)}")
        # 3. Si hay un error crítico de recursos, reseteamos el grafo para obligar a re-conectar
        if "ClosedResourceError" in str(e) or "Connection closed" in str(e):
            global_graph = None
            logger.warning("🔄 Grafo de Telegram reseteado por error de conexión.")
            await update.message.reply_text("🔄 He tenido un problema de conexión, pero ya lo he solucionado. Por favor, repite tu pregunta.")
        else:
            await update.message.reply_text("⚠️ Ocurrió un error interno procesando tu solicitud.")


async def post_init(application: ApplicationBuilder):
    """
    Lógica de inicialización posterior al arranque de la aplicación.
    """
    await initialize_agent()


if __name__ == '__main__':
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("Falta TELEGRAM_BOT_TOKEN en las variables de entorno.")
        exit(1)

    logger.info("Iniciando bot de Telegram...")
    
    app = ApplicationBuilder().token(token).post_init(post_init).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    app.run_polling()
