import os
import logging
import asyncio
from dotenv import load_dotenv
from telegram import Update, constants
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# --- IMPORTAMOS EL CEREBRO UNIFICADO (Lo mismo que usa Chainlit) ---
from langchain_core.messages import HumanMessage, AIMessage
# Asegúrate de importar desde donde definiste la lógica del Router/Clasificador
from agent_core.graph import build_graph 
from agent_core.main import build_context # <--- ESTO ES CLAVE

# Cargar variables de entorno
load_dotenv()

# Configuración de Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- ESTADO GLOBAL ---
global_graph = None
user_histories = {} 

async def initialize_agent():
    """Construye el grafo completo (Router + SQL + API)."""
    global global_graph
    
    if global_graph:
        return global_graph

    try:
        print("🔌 [Telegram] Inicializando Cerebro Unificado...")
        
        # 1. Construimos el contexto (Carga herramientas, prompts, conecta MCP)
        # Esto reutiliza la lógica robusta que ya hiciste para la Web
        context = await build_context()
        
        # 2. Construimos el grafo con ese contexto
        # Usamos unpacking (**) porque build_context devuelve dict {'tools': ..., 'system_prompt': ...}
        # y build_graph espera (tools, system_prompt)
        global_graph = build_graph(**context)
        
        print("🧠 [Telegram] Agente listo (con Clasificador + SQL + API).")
        return global_graph

    except Exception as e:
        print(f"❌ [Telegram] Error fatal iniciando agente: {e}")
        raise e

async def send_long_message(update: Update, text: str):
    """
    Rompe mensajes largos en trozos compatibles con Telegram (4096 chars).
    Intenta respetar bloques de código markdown si es posible (básico).
    """
    MAX_LENGTH = 4000 # Dejamos margen
    
    # Si es corto, enviamos directo con Markdown
    if len(text) <= MAX_LENGTH:
        try:
            await update.message.reply_text(text, parse_mode=constants.ParseMode.MARKDOWN)
        except Exception:
            # Fallback si el Markdown está roto (común en LLMs)
            await update.message.reply_text(text)
        return

    # Si es largo, lo partimos
    for i in range(0, len(text), MAX_LENGTH):
        chunk = text[i:i + MAX_LENGTH]
        try:
            await update.message.reply_text(chunk)
        except Exception as e:
            print(f"Error enviando chunk: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Hola, soy tu Agente IA**\n"
        "Puedo consultar la base de datos y APIs externas.\n"
        "¿En qué te ayudo?",
        parse_mode=constants.ParseMode.MARKDOWN
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    
    # UX: "Escribiendo..."
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)

    # 1. Lazy Init
    if not global_graph:
        await initialize_agent()
        
    # 2. Historial (Memoria volátil)
    if chat_id not in user_histories:
        user_histories[chat_id] = []
    
    history = user_histories[chat_id]
    history.append(HumanMessage(content=user_text))

    print(f"📩 [Chat {chat_id}] Procesando: {user_text[:50]}...")

    try:
        inputs = {"messages": history}
        
        # 3. Invocación
        response = await global_graph.ainvoke(inputs)
        
        # 4. Procesar respuesta
        final_messages = response.get("messages", [])
        if final_messages:
            last_msg = final_messages[-1]
            ai_content = last_msg.content
            
            # Actualizamos historial
            user_histories[chat_id] = final_messages
            
            # 5. Enviar con seguridad (Largo + Markdown)
            await send_long_message(update, ai_content)
        else:
            await update.message.reply_text("🤔 ...")

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        await update.message.reply_text("⚠️ Ocurrió un error interno.")

async def post_init(application: ApplicationBuilder):
    await initialize_agent()

if __name__ == '__main__':
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ Falta TELEGRAM_BOT_TOKEN en .env")
        exit(1)

    print("🚀 Iniciando Telegram Bot...")
    application = ApplicationBuilder().token(token).post_init(post_init).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("📡 Escuchando...")
    application.run_polling()
