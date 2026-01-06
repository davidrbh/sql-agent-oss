import asyncio
import os
import yaml
import time
from typing import List, Optional
from sqlalchemy import text

# ✅ Importaciones para Estructura Estricta
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from sql_agent.config.loader import ConfigLoader
from sql_agent.database.connection import DatabaseManager
from sql_agent.database.inspector import SchemaExtractor

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
OUTPUT_PATH = os.path.join(BASE_DIR, 'data', 'dictionary.yaml')

# --- DEFINICIÓN DEL MOLDE (SCHEMA) ---
# Esto le dice a Gemini exactamente qué estructura debe llenar.
class ColumnSchema(BaseModel):
    name: str = Field(description="El nombre exacto de la columna en la base de datos")
    description: str = Field(description="Descripción funcional de qué datos guarda esta columna")
    is_active: bool = Field(description="True si es relevante para el negocio, False si es técnica (logs, migraciones)")

class TableSchema(BaseModel):
    friendly_name: str = Field(description="Un nombre corto y legible para humanos")
    description: str = Field(description="Explicación detallada de para qué sirve esta tabla en el negocio")
    columns: List[ColumnSchema] = Field(description="Lista de columnas analizadas")

class SemanticHydrator:
    """
    Clase encargada de orquestar la creación del Diccionario de Datos.
    Versión: Gemini Structured Outputs (Nativo y Estricto)
    """
    
    def __init__(self, table_limit=5):
        self.table_limit = table_limit
        self.context = ConfigLoader.load_context()
        self.settings = ConfigLoader.load_settings()
        
        # 1. Instanciamos el modelo base
        llm_base = ChatGoogleGenerativeAI(
            model="gemini-3-flash-preview", # Usamos el 2.0 que es rápido y soporta esto nativamente
            temperature=0,
            max_retries=2
        )
        
        # 2. ACTIVAMOS EL MODO ESTRUCTURADO 🛡️
        # Esto inyecta el JSON Schema en la API de Google automáticamente.
        self.structured_llm = llm_base.with_structured_output(TableSchema)

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

    async def run(self):
        app_name = self.settings.get('app', {}).get('name', 'App')
        print(f"🚀 Iniciando Hidratación (Modo Estructurado Nativo) para {app_name}...")
        
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
            
            # Convertimos sample a string, manejando bytes o fechas raras
            samples_str = str(samples) if samples else "Sin datos."

            prompt = ChatPromptTemplate.from_template(
                """
                Eres un Data Architect experto analizando la base de datos de "{business_context}".
                
                Analiza la tabla: '{table_name}'
                
                COLUMNAS:
                {columns_info}
                
                DATOS DE MUESTRA:
                {sample_data}
                
                Genera la documentación siguiendo estrictamente el esquema solicitado.
                """
            )

            # Creamos la cadena usando el LLM estructurado
            chain = prompt | self.structured_llm
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Invocar a la IA
                    # Gracias a with_structured_output, 'response' YA ES un objeto TableSchema
                    # No es texto, no es JSON string, es un Objeto Python listo.
                    response_obj = await chain.ainvoke({
                        "business_context": self.context,
                        "table_name": table_name,
                        "columns_info": cols_text,
                        "sample_data": samples_str
                    })
                    
                    # Convertir el objeto Pydantic a Diccionario normal para guardarlo
                    ai_data = response_obj.model_dump()

                    semantic_dict["tables"].append({"name": table_name, **ai_data})
                    print("   ✅ Documentada (Estructura Perfecta).")
                    
                    await asyncio.sleep(4) # Pausa anti-bloqueo google
                    break 

                except Exception as e:
                    error_msg = str(e)
                    if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                        wait_time = 20
                        print(f"   ⏳ Cuota llena. Esperando {wait_time}s... (Intento {attempt+1})")
                        await asyncio.sleep(wait_time)
                    else:
                        print(f"   ❌ Error: {e}")
                        await asyncio.sleep(2)

        # Guardar en YAML limpio
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(semantic_dict, f, allow_unicode=True, sort_keys=False)
            
        print(f"\n💾 Diccionario generado en: {OUTPUT_PATH}")

if __name__ == "__main__":
    asyncio.run(SemanticHydrator().run())