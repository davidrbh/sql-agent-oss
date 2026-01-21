# scripts/generate_dictionary.py
import asyncio
import os
import sys
import yaml
import json
import re
import aiomysql
from typing import List, Dict, Any
from pathlib import Path
from dotenv import load_dotenv

# --- Configuración de Rutas y Path ---
# La ruta a 'src' se proveerá mediante la variable de entorno PYTHONPATH
# al ejecutar el script, para mantenerlo consistente con el resto de la app.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Cargar variables de entorno desde el archivo .env en la raíz
load_dotenv(PROJECT_ROOT / ".env")

# Importar usando la ruta relativa a 'src'
from agent_core.llm.factory import LLMFactory
from langchain_core.prompts import ChatPromptTemplate

# --- Lógica Principal del Script ---

class SemanticHydrator:
    """
    Hidratador Semántico v3 (Modernizado).
    Compila 'business_context.yaml' + Esquema de BD real en 'dictionary.yaml'
    para ser consumido por el Agente SQL.
    """
    def __init__(self, context_path: Path, output_path: Path):
        self.context_path = context_path
        self.output_path = output_path
        self.context = self._load_business_context()
        self.llm = LLMFactory.create(temperature=0)
        self.db_pool = None

    def _load_business_context(self) -> Dict[str, Any]:
        """Carga y valida el archivo de contexto de negocio."""
        print(f"   📂 Buscando contexto de negocio en: {self.context_path}")
        if not self.context_path.is_file():
            print(f"❌ Error Crítico: El archivo '{self.context_path.name}' NO EXISTE en la ruta esperada ({self.context_path}).")
            sys.exit(1)
        
        try:
            with open(self.context_path, 'r', encoding='utf-8') as f:
                context = yaml.safe_load(f) or {}
            print("   ✅ Contexto de negocio cargado correctamente.")
            return context
        except Exception as e:
            print(f"   ❌ Error leyendo o parseando el archivo YAML: {e}")
            sys.exit(1)

    async def _create_db_pool(self):
        """Crea un pool de conexiones a la base de datos."""
        try:
            print("   🔌 Creando pool de conexiones a la base de datos...")
            self.db_pool = await aiomysql.create_pool(
                host=os.getenv("DB_HOST"),
                port=int(os.getenv("DB_PORT", 3306)),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                db=os.getenv("DB_NAME"),
                autocommit=True
            )
            print("   ✅ Pool de conexiones creado.")
        except Exception as e:
            print(f"   ❌ Error al conectar con la base de datos: {e}")
            print("      Asegúrate de que las variables DB_* en tu .env son correctas y la BD está accesible.")
            sys.exit(1)

    async def _get_sample_data(self, table_name: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Obtiene filas de muestra de una tabla para ver el formato real."""
        if not self.db_pool:
            return []
            
        async with self.db_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                try:
                    clean_name = table_name.split('.')[-1]
                    await cursor.execute(f"SELECT * FROM `{clean_name}` LIMIT {limit}")
                    rows = await cursor.fetchall()
                    # Convertir todos los valores a string para evitar errores de serialización
                    return [{k: str(v) for k, v in row.items()} for row in rows]
                except Exception as e:
                    print(f"   ⚠️ No se pudo obtener muestra de '{table_name}': {e}")
                    return []

    def _clean_json_string(self, content: str) -> str:
        """Extrae un bloque de código JSON de una respuesta de texto del LLM."""
        if isinstance(content, list):
            content = "".join([str(x) for x in content])
        content = str(content)
        
        match = re.search(r"```(?:json)?(.*)```", content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return content.strip()

    def _format_model_metadata(self, model: dict) -> str:
        """Convierte la definición del modelo YAML en texto para el prompt del LLM."""
        parts = [f"MODELO LÓGICO: {model.get('name')}"]
        if 'dimensions' in model:
            parts.append("\nDIMENSIONES (Atributos):")
            for dim in model['dimensions']:
                desc = f"- {dim['name']} (Columna DB: {dim.get('col')}) : {dim.get('description', '')}"
                parts.append(desc)
        if 'measures' in model:
            parts.append("\nMEDIDAS (Métricas Numéricas):")
            for measure in model['measures']:
                desc = f"- {measure['name']}: {measure.get('description', '')}"
                parts.append(desc)
        return "\n".join(parts)

    async def run(self):
        """Ejecuta el proceso completo de hidratación."""
        print(f"\n🚀 Iniciando Hidratación Semántica...")

        # Validación 1: Verificar si el diccionario ya existe
        if self.output_path.is_file():
            print(f"✅ El diccionario ya existe en: {self.output_path}")
            print("   ⏩ Saltando generación (Optimization).")
            return

        await self._create_db_pool()

        models = self.context.get('models', [])
        if not models:
            print("❌ Error: No se encontró la sección 'models' en business_context.yaml")
            if self.db_pool: await self.db_pool.close()
            return

        hydrated_dict = {"tables": []}
        print(f"📊 Procesando {len(models)} modelos definidos...")

        for i, model in enumerate(models):
            table_source = model.get('source')
            if not table_source:
                continue
            
            print(f"\n🔍 [{i+1}/{len(models)}] Hidratando modelo: {model['name']} (Tabla: {table_source})")
            
            samples = await self._get_sample_data(table_source)
            model_metadata = self._format_model_metadata(model)
            
            prompt = ChatPromptTemplate.from_template(
                """
                Eres un Arquitecto de Datos experto. Tu trabajo es generar la documentación para un Agente SQL,
                fusionando la información SEMÁNTICA (reglas de negocio) con la FÍSICA (muestras de datos reales).

                --- CONTEXTO SEMÁNTICO (Lo que el negocio define) ---
                {model_metadata}

                --- MUESTRA DE DATOS REALES (Lo que la base de datos contiene) ---
                {sample_data}

                --- TAREA ---
                Genera un bloque de código JSON que describa esta tabla. En la descripción de cada columna,
                DEBES fusionar la descripción del negocio con ejemplos de los datos reales.
                Sé conciso pero informativo.

                --- FORMATO DE SALIDA (Solo el bloque de código JSON) ---
                ```json
                {{
                    "friendly_name": "Nombre legible para la tabla",
                    "description": "Descripción funcional completa de la tabla.",
                    "columns": [
                        {{
                            "name": "nombre_columna_fisica",
                            "description": "Descripción de la columna fusionada con ejemplos. ej: 'Estado del pedido (Valores: pending, shipped, ...)'"
                        }}
                    ]
                }}
                ```
                """
            )
            chain = prompt | self.llm
            
            response = await chain.ainvoke({
                "model_metadata": model_metadata,
                "sample_data": str(samples)
            })
            
            json_str = self._clean_json_string(response.content)
            try:
                ai_data = json.loads(json_str)
                hydrated_dict["tables"].append({"name": table_source.split('.')[-1], **ai_data})
                print("   ✅ Modelo hidratado con éxito.")
            except json.JSONDecodeError:
                print(f"   ❌ Error: El LLM devolvió un JSON inválido. Saltando este modelo.")
                print(f"      Respuesta recibida: {json_str}")

        if self.db_pool:
            self.db_pool.close()
            await self.db_pool.wait_closed()
            print("\n   🔌 Pool de conexiones cerrado.")

        # Guardar el diccionario final
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, 'w', encoding='utf-8') as f:
            yaml.dump(hydrated_dict, f, allow_unicode=True, sort_keys=False, indent=2)
            
        print(f"\n💾 Diccionario Semántico Maestro generado en: {self.output_path}")


async def main():
    """Punto de entrada principal del script."""
    context_file = PROJECT_ROOT / "config" / "business_context.yaml"
    dictionary_file = PROJECT_ROOT / "data" / "dictionary.yaml"
    
    hydrator = SemanticHydrator(context_path=context_file, output_path=dictionary_file)
    await hydrator.run()

if __name__ == "__main__":
    # Inicia el bucle de eventos de asyncio para ejecutar la función main
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProceso interrumpido por el usuario.")
