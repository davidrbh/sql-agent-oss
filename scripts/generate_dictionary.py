import asyncio
import sys
import os

# Ajuste de path para encontrar 'src'
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from sql_agent.semantic.hydrator import SemanticHydrator

async def main():
    print("--- 🧠 Iniciando Generador de Diccionario Semántico (V2) ---")
    
    try:
        # ✅ CAMBIO: Ya no pasamos argumentos. 
        # El hidratador leerá 'models' de tu business_context.yaml automáticamente.
        hydrator = SemanticHydrator() 
        
        await hydrator.run()
        
    except Exception as e:
        print(f"❌ Error Fatal: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())