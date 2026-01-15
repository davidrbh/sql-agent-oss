import asyncio
import os
import yaml
import json
import re
from sqlalchemy import text
from langchain_core.prompts import ChatPromptTemplate

# Importamos la Fábrica y Configuración
from sql_agent.llm.factory import LLMFactory
from sql_agent.config.loader import ConfigLoader
# from sql_agent.database.connection import DatabaseManager # REPLACE
from sql_agent.utils.mcp_client import mcp_manager
from sql_agent.database.inspector import SchemaExtractor

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
OUTPUT_PATH = os.path.join(BASE_DIR, 'data', 'dictionary.yaml')

class SemanticHydrator:
    """
    Hidratador Semántico v2.
    Compila el 'business_context.yaml' (Estándar Universal) + Esquema DB
    en un 'dictionary.yaml' optimizado para el Agente.
    """
    
    def __init__(self):
        print("   🔧 Inicializando Hidratador (Modo Directo)...")
        
        # 1. Calcular la ruta absoluta al archivo config/business_context.yaml
        # (Asumiendo que hydrator.py está en src/sql_agent/semantic/)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, "../../../"))
        config_path = os.path.join(project_root, "config", "business_context.yaml")
        
        print(f"   📂 Buscando archivo en: {config_path}")

        # 2. Verificar existencia
        if not os.path.exists(config_path):
            print(f"   ❌ ERROR CRÍTICO: El archivo NO EXISTE en la ruta calculada.")
            print(f"      Ruta actual de ejecución: {os.getcwd()}")
            self.context = {}
            return

        # 3. Leer y Parsear
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self.context = yaml.safe_load(f) or {}
                
            # 4. Debugging: ¿Qué llaves encontró?
            keys_found = list(self.context.keys())
            print(f"   🔑 Claves encontradas en el YAML: {keys_found}")
            
            if 'models' in keys_found:
                print(f"   ✅ Estructura V2.5 detectada correctamente ({len(self.context['models'])} modelos).")
            elif 'tables' in keys_found:
                print(f"   ⚠️ ALERTA: Estás usando el formato VIEJO (v17) con 'tables'. Necesitas guardar el contenido v2.5.")
            else:
                print(f"   ⚠️ ALERTA: El archivo no tiene 'models' ni 'tables'. ¿Está guardado?")

        except Exception as e:
            print(f"   ❌ Error leyendo el YAML: {e}")
            self.context = {}

        self.llm = LLMFactory.create(temperature=0)

    async def _get_sample_data(self, table_name: str, limit: int = 3):
        """Obtiene 3 filas de muestra para que el Agente vea el formato real."""
        try:
            # Extraemos solo el nombre de la tabla si tiene esquema (ej: db.tabla -> tabla)
            clean_name = table_name.split('.')[-1]
            sql = f"SELECT * FROM {clean_name} LIMIT {limit}"
            
            result_json = await mcp_manager.execute_query(sql)
            rows = json.loads(result_json)
            
            if not rows: return []
            
            # Convertimos a string para evitar errores de serialización
            # Si MCP devuelve JSON, los tipos ya son JS-compatible (str, num, etc)
            # Aseguramos formato [{k: str(v)}]
            return [{k: str(v) for k, v in row.items()} for row in rows]
            
        except Exception as e:
            print(f"   ⚠️ No se pudo obtener muestra de '{table_name}': {e}")
            return []

    def _clean_json_string(self, content: str) -> str:
        """Limpieza robusta para extraer JSON de la respuesta del LLM."""
        if isinstance(content, list):
            content = "".join([str(x) for x in content])
        content = str(content)
        # Buscar bloque ```json ... ```
        if "```" in content:
            pattern = r"```(?:json)?(.*?)```"
            matches = re.findall(pattern, content, re.DOTALL)
            if matches:
                content = matches[0]
        return content.strip()

    def _format_model_metadata(self, model: dict) -> str:
        """
        Convierte la definición del modelo (YAML) en texto explicativo para el Prompt.
        """
        text_parts = [f"MODELO LÓGICO: {model.get('name')}"]
        
        # 1. Dimensiones (Columnas con significado)
        if 'dimensions' in model:
            text_parts.append("\nDIMENSIONES DEFINIDAS (Atributos):")
            for dim in model['dimensions']:
                desc = f"- {dim['name']} (Columna DB: {dim.get('col')})"
                if 'description' in dim:
                    desc += f": {dim['description']}"
                if 'allowed_values' in dim:
                    desc += f" [Valores Permitidos: {dim['allowed_values']}]"
                if 'sql' in dim:
                    desc += f" [Lógica SQL Virtual: {dim['sql']}]"
                text_parts.append(desc)

        # 2. Medidas (KPIs y Métricas)
        if 'measures' in model:
            text_parts.append("\nMEDIDAS (Métricas Numéricas):")
            for measure in model['measures']:
                desc = f"- {measure['name']}"
                if 'col' in measure:
                    desc += f" (Basado en columna: {measure['col']})"
                if 'sql' in measure:
                    desc += f" (Fórmula SQL: {measure['sql']})"
                if 'description' in measure:
                    desc += f": {measure['description']}"
                text_parts.append(desc)
        
        return "\n".join(text_parts)

    async def run(self):
        print(f"🚀 Iniciando Hidratación Semántico (v2.5 Compatible)...")
        
        # 1. Leer Modelos del Contexto de Negocio
        models = self.context.get('models', [])
        if not models:
            print("❌ Error: No se encontraron 'models' en business_context.yaml")
            return

        semantic_dict = {"tables": []}
        
        print(f"📊 Procesando {len(models)} modelos definidos en la Capa Semántica.")

        for i, model in enumerate(models):
            table_source = model['source']
            clean_table_name = table_source.split('.')[-1]
            
            print(f"\n🔍 [{i+1}/{len(models)}] Compilando Modelo: {model['name']} -> Tabla: {clean_table_name}")
            
            # Obtener datos reales de la DB (Introspección Física)
            samples = await self._get_sample_data(clean_table_name)
            
            # Preparar la "Ficha Técnica" para el LLM
            model_metadata = self._format_model_metadata(model)
            
            prompt = ChatPromptTemplate.from_template(
                """
                Actúa como un Arquitecto de Datos experto.
                Tu trabajo es generar la documentación final para un Agente SQL.
                
                Debes fusionar la información de la CAPA SEMÁNTICA (Reglas de Negocio) con los DATOS REALES.

                --- INPUTS ---
                1. DEFINICIÓN SEMÁNTICA (Lo que el negocio dice):
                {model_metadata}

                2. MUESTRA DE DATOS REALES (Lo que la base de datos tiene):
                {sample_data}

                --- INSTRUCCIONES CRÍTICAS ---
                1. Genera un JSON que describa esta tabla.
                2. En la descripción de las columnas, DEBES incluir las reglas de negocio (Enums, Fórmulas).
                3. Si hay una medida marcada como "FUENTE DE VERDAD", resáltalo en mayúsculas en la descripción.
                4. Si hay dimensiones con 'allowed_values', inclúyelos explícitamente (ej: "1=Activo").
                5. Si hay 'sql' personalizado (campos virtuales), agrégalos como columnas virtuales en la documentación.

                --- OUTPUT REQUERIDO (JSON) ---
                {{
                    "friendly_name": "Nombre legible",
                    "description": "Descripción funcional completa.",
                    "columns": [
                        {{
                            "name": "nombre_columna_fisica_o_virtual",
                            "description": "Descripción rica + Reglas + Enums",
                            "is_active": true
                        }}
                    ]
                }}
                """
            )

            chain = prompt | self.llm
            
            # Reintentos para robustez
            for attempt in range(3):
                try:
                    response = await chain.ainvoke({
                        "model_metadata": model_metadata,
                        "sample_data": str(samples)
                    })
                    
                    json_str = self._clean_json_string(response.content)
                    ai_data = json.loads(json_str)
                    
                    # Guardamos el nombre real de la tabla para que el SQL funcione
                    semantic_dict["tables"].append({"name": clean_table_name, **ai_data})
                    print("   ✅ Compilación Exitosa.")
                    await asyncio.sleep(1) # Rate limit friendly
                    break 
                except Exception as e:
                    print(f"   ⚠️ Reintentando ({attempt+1})... Error: {e}")
                    await asyncio.sleep(2)

        # Guardar el Cerebro Final
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(semantic_dict, f, allow_unicode=True, sort_keys=False)
            
        print(f"\n💾 Diccionario Maestro generado en: {OUTPUT_PATH}")

if __name__ == "__main__":
    asyncio.run(SemanticHydrator().run())