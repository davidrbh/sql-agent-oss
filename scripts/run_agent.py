import asyncio
import sys
import os

# Ajuste de path para encontrar 'src'
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from sql_agent.graph import build_graph

async def main():
    print("--- 🤖 SQL AGENT OSS (Gemini Powered) ---")
    print("Iniciando sistemas...")
    
    # Construimos el cerebro
    agent = build_graph()
    
    print("✅ Agente listo. Escribe 'salir' para terminar.\n")
    
    while True:
        try:
            user_input = input("USER > ")
            if user_input.lower() in ["salir", "exit", "quit"]:
                print("👋 Hasta luego!")
                break
            
            print("⏳ Pensando...")
            
            # Ejecutamos el grafo con la pregunta del usuario
            # ainvoke es la forma asíncrona de llamar a LangGraph
            inputs = {"question": user_input, "messages": []}
            
            # Streaming de eventos (opcional, para ver qué hace)
            # Aquí usamos invoke simple para obtener el resultado final
            result = await agent.ainvoke(inputs)
            
            # Extraemos el último mensaje de la IA
            final_response = result["messages"][-1].content
            
            print(f"\n🤖 AI > {final_response}\n")
            print("-" * 50)
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
