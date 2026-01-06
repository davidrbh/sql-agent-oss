import asyncio
import os
import yaml
import json
import re
from sqlalchemy import text

# Importamos la Fábrica
from sql_agent.llm.factory import LLMFactory
from sql_agent.config.loader import ConfigLoader
from sql_agent.database.connection import DatabaseManager
from sql_agent.database.inspector import SchemaExtractor
from langchain_core.prompts import ChatPromptTemplate

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
OUTPUT_PATH = os.path.join(BASE_DIR, 'data', 'dictionary.yaml')

class SemanticHydrator:
    """
    Generador de Diccionario (Versión Universal / DeepSeek Compatible).
    Usa prompt engineering en lugar de funciones nativas para asegurar compatibilidad.
    """
    
    def __init__(self, table_limit=None): 
        self.table_limit = table_limit
        self.context = ConfigLoader.load_context()
        self.settings = ConfigLoader.load_settings()
        
        # Pedimos el modelo (DeepSeek/Google)
        self.llm = LLMFactory.create(temperature=0)

    async def _get_sample_data(self, table_name: str, limit: int = 3):
        engine = DatabaseManager.get_engine()
        async with engine.connect() as conn:
            try:
                query = text(f"SELECT * FROM {table_name} LIMIT {limit}")
                result = await conn.execute(query)
                rows = result.fetchall()
                keys = result.keys()
                return [{key: str(val) for key, val in zip(keys, row)} for row in rows]
            except Exception:
                return []

    def _clean_json_string(self, content: str) -> str:
        """Limpia la respuesta para extraer JSON válido."""
        if isinstance(content, list):
            content = "".join([str(x) for x in content])
        content = str(content)
        
        # Eliminar bloques markdown ```json ... ```
        if "```" in content:
            pattern = r"```(?:json)?(.*?)```"
            matches = re.findall(pattern, content, re.DOTALL)
            if matches:
                content = matches[0]
        return content.strip()

    async def run(self):
        app_name = self.settings.get('app', {}).get('name', 'App')
        print(f"🚀 Iniciando Hidratación (Modo Universal) para {app_name}...")
        
        raw_schema = await SchemaExtractor.get_schema_info()
        tables = list(raw_schema.keys())
        
        semantic_dict = {"tables": []}
        tables_to_process = tables[:self.table_limit]
        
        print(f"📊 Procesando {len(tables_to_process)} tablas.")

        for i, table_name in enumerate(tables_to_process):
            print(f"\n🔍 [{i+1}/{len(tables_to_process)}] Analizando: {table_name}")
            
            columns = raw_schema[table_name]
            cols_text = "\n".join([f"- {c['name']} ({c['type']})" for c in columns])
            samples = await self._get_sample_data(table_name)
            samples_str = str(samples) if samples else "Sin datos."

            # Prompt explícito pidiendo JSON
            prompt = ChatPromptTemplate.from_template(
                """
                Actúa como un Arquitecto de Datos.
                CONTEXTO: "{business_context}"
                TABLA: '{table_name}'
                COLUMNAS: {columns_info}
                MUESTRA: {sample_data}
                
                Genera un objeto JSON válido con la documentación.
                FORMATO REQUERIDO:
                {{
                    "friendly_name": "Nombre legible",
                    "description": "Explicación funcional",
                    "columns": [
                        {{
                            "name": "nombre_columna",
                            "description": "Que guarda",
                            "is_active": true
                        }}
                    ]
                }}
                """
            )

            chain = prompt | self.llm
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = await chain.ainvoke({
                        "business_context": self.context,
                        "table_name": table_name,
                        "columns_info": cols_text,
                        "sample_data": samples_str
                    })
                    
                    # Limpieza manual (Universal)
                    json_str = self._clean_json_string(response.content)
                    ai_data = json.loads(json_str)
                    
                    semantic_dict["tables"].append({"name": table_name, **ai_data})
                    print("   ✅ Documentada.")
                    
                    await asyncio.sleep(1) # Cortesía con la API
                    break 

                except json.JSONDecodeError:
                    print(f"   ⚠️ Error de JSON (Intento {attempt+1}). Reintentando...")
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"   ❌ Error: {e}")
                    await asyncio.sleep(2)

        # Guardar
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(semantic_dict, f, allow_unicode=True, sort_keys=False)
            
        print(f"\n💾 Diccionario generado en: {OUTPUT_PATH}")

if __name__ == "__main__":
    asyncio.run(SemanticHydrator().run())