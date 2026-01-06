import os
import sys
# Ajuste de path para importar configuración
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from sql_agent.config.loader import ConfigLoader
import google.generativeai as genai

def list_available_models():
    # 1. Cargar la Key
    settings = ConfigLoader.load_settings() # Solo para asegurar carga de entorno
    api_key = os.environ.get("GOOGLE_API_KEY")
    
    if not api_key:
        print("❌ Error: No se encontró GOOGLE_API_KEY en el entorno.")
        return

    print(f"🔑 Probando llave: {api_key[:5]}...{api_key[-3:]}")
    
    # 2. Configurar cliente nativo
    genai.configure(api_key=api_key)

    print("\n📡 Consultando a Google qué modelos tienes habilitados...")
    try:
        count = 0
        for m in genai.list_models():
            # Filtramos solo los que sirven para generar texto (generateContent)
            if 'generateContent' in m.supported_generation_methods:
                print(f"   ✅ Disponible: {m.name}")
                count += 1
        
        if count == 0:
            print("⚠️ Tu llave conecta, pero no tienes modelos de generación disponibles.")
            print("   Solución: Ve a Google AI Studio y acepta los términos de uso.")
            
    except Exception as e:
        print(f"❌ Error crítico de conexión: {e}")

if __name__ == "__main__":
    list_available_models()