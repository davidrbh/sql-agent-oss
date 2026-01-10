import asyncio
import sys
import os

# Ajuste de path para encontrar 'src'
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

# ✅ NUEVO: Importamos HumanMessage para guardar lo que dice el usuario
from langchain_core.messages import HumanMessage
from sql_agent.graph import build_graph
from sql_agent.database.connection import DatabaseManager  # Importar para limpieza robusta

async def main():
    print("--- 🤖 SQL AGENT OSS (DeepSeek Powered) ---")
    print("Iniciando sistemas...")
    
    # Construimos el cerebro
    agent = build_graph()
    
    # ✅ MEMORIA A LARGO PLAZO (Mientras dure el script)
    chat_history = [] 
    
    print("✅ Agente listo. Escribe 'salir' para terminar.\n")
    
    try:
        while True:
            try:
                user_input = input("USER > ")
                if user_input.lower() in ["salir", "exit", "quit"]:
                    print("👋 Hasta luego!")
                    break
                
                print("⏳ Pensando...")
                
                # 1. Guardamos tu pregunta en la historia
                chat_history.append(HumanMessage(content=user_input))
                
                # 2. Le pasamos TODA la historia al agente
                inputs = {
                    "question": user_input, 
                    "messages": chat_history 
                }
                
                # Ejecutamos el grafo
                result = await agent.ainvoke(inputs)
                
                # 3. Actualizamos la historia con la respuesta del Agente
                # result["messages"] contiene la lista actualizada (Tu pregunta + Respuesta IA)
                chat_history = result["messages"]
                
                # Extraemos el último mensaje para mostrarlo
                final_response = chat_history[-1].content
                
                print(f"\n🤖 AI > {final_response}\n")
                print("-" * 50)
                
            except KeyboardInterrupt:
                print("\n👋 Interrupción de teclado detectada.")
                break
            except Exception as e:
                print(f"❌ Error en chat: {e}")
                import traceback
                traceback.print_exc()

    finally:
        # ✅ LIMPIEZA ROBUSTA DE RECURSOS
        # Esto previene el error 'Event loop is closed' al cerrar aiomysql
        print("\n🧹 Cerrando conexiones de base de datos...")
        await DatabaseManager.close()

if __name__ == "__main__":
    asyncio.run(main())