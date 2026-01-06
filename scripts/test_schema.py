import asyncio
import sys
import os
import json

# Ajuste de path para importar src
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

# 1. IMPORTACIÓN CORREGIDA (inspector en lugar de schema)
from sql_agent.database.inspector import SchemaExtractor
# 2. Importamos el nuevo Loader para probar que lee la config
from sql_agent.config.loader import ConfigLoader

async def main():
    print("--- 🔬 Test de Integración: Infraestructura y Configuración ---")
    
    # A. Probar carga de Configuración
    print("\n1. ⚙️  Probando Carga de Configuración...")
    context = ConfigLoader.load_context()
    settings = ConfigLoader.load_settings()
    
    print(f"   ✅ App Name: {settings.get('app', {}).get('name')}")
    print(f"   ✅ Contexto cargado ({len(context)} caracteres).")
    
    # B. Probar conexión y extracción
    print("\n2. 🕵️  Probando Inspector de Base de Datos...")
    try:
        schema = await SchemaExtractor.get_schema_info()
        print(f"   ✅ Éxito: Se detectaron {len(schema)} tablas.")
        
        # Guardar log en la nueva carpeta de logs
        log_path = os.path.join(os.path.dirname(__file__), '..', 'logs', 'schema_test.json')
        with open(log_path, "w") as f:
            json.dump(schema, f, indent=2, default=str)
        print(f"   💾 Log guardado en: logs/schema_test.json")
        
    except Exception as e:
        print(f"   ❌ Error crítico: {e}")

if __name__ == "__main__":
    asyncio.run(main())