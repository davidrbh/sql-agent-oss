import sys
import os
import yaml
from typing import List, Optional, Literal, Union
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import create_engine, inspect, text
from dotenv import load_dotenv

# Cargar variables de entorno (.env)
load_dotenv()

# --- 1. MODELOS DE DATOS (PYDANTIC) ---
# Representan la estructura exacta de tu YAML v2.5

class EntityRef(BaseModel):
    name: str
    type: Literal['primary', 'foreign', 'unique']
    col: str

class Dimension(BaseModel):
    name: str
    type: str
    col: Optional[str] = None
    sql: Optional[str] = None # Para dimensiones calculadas
    description: Optional[str] = None

class Measure(BaseModel):
    name: str
    type: str
    col: Optional[str] = None
    sql: Optional[str] = None
    description: Optional[str] = None

class DataModel(BaseModel):
    name: str
    source: str # Ej: bnplsite_credivibes.users
    entities: List[EntityRef] = []
    dimensions: List[Dimension] = []
    measures: List[Measure] = []

class BusinessContext(BaseModel):
    version: str
    project: str
    models: List[DataModel]

# --- 2. LÓGICA DE VALIDACIÓN ---

def get_db_engine():
    """Crea la conexión a MySQL usando las variables de entorno"""
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "3306")
    dbname = os.getenv("DB_NAME", "bnplsite_credivibes") # Default
    
    # Usamos pymysql como driver
    uri = f"mysql+pymysql://{user}:{password}@{host}:{port}/{dbname}"
    return create_engine(uri)

def validate_structure(yaml_path: str) -> BusinessContext:
    print("📄 Leyendo archivo YAML...")
    with open(yaml_path, 'r', encoding='utf-8') as f:
        raw_data = yaml.safe_load(f)
    
    try:
        context = BusinessContext(**raw_data)
        print("✅ Estructura YAML válida (Sintaxis Correcta).")
        return context
    except ValidationError as e:
        print("❌ ERROR DE SINTAXIS EN YAML:")
        print(e)
        sys.exit(1)

def validate_physical_schema(context: BusinessContext):
    print("\n🔌 Conectando a Base de Datos para Auditoría...")
    try:
        engine = get_db_engine()
        inspector = inspect(engine)
    except Exception as e:
        print(f"❌ Error conectando a DB: {e}")
        sys.exit(1)

    print("🕵️‍♂️ Iniciando validación cruzada (YAML vs MySQL)...")
    
    errors_found = False

    for model in context.models:
        # Extraer nombre de tabla (maneja esquema.tabla o solo tabla)
        full_table_name = model.source
        if '.' in full_table_name:
            table_name = full_table_name.split('.')[-1]
        else:
            table_name = full_table_name
        
        # 1. Validar Tabla
        if not inspector.has_table(table_name):
            print(f"   ❌ [FATAL] Modelo '{model.name}': La tabla física '{table_name}' NO EXISTE en la DB.")
            errors_found = True
            continue # No podemos validar columnas si la tabla no existe
        
        # Obtener columnas reales de la DB
        db_columns = [c['name'] for c in inspector.get_columns(table_name)]
        
        print(f"   🔍 Analizando modelo '{model.name}' ({table_name})...")

        # 2. Validar Dimensiones
        for dim in model.dimensions:
            if dim.col and dim.col not in db_columns:
                print(f"      ⚠️ Error en Dimensión '{dim.name}': Columna '{dim.col}' no encontrada en tabla.")
                errors_found = True
        
        # 3. Validar Medidas
        for measure in model.measures:
            if measure.col and measure.col not in db_columns:
                print(f"      ⚠️ Error en Medida '{measure.name}': Columna '{measure.col}' no encontrada en tabla.")
                errors_found = True
            # Nota: Si usa 'sql' en lugar de 'col', no lo validamos aquí (es más complejo)

    if errors_found:
        print("\n❌ LA VALIDACIÓN FALLÓ. Corrige los errores en business_context.yaml antes de continuar.")
        sys.exit(1)
    else:
        print("\n🎉 ¡ÉXITO! El contexto de negocio está sincronizado al 100% con la base de datos.")

# --- MAIN ---
if __name__ == "__main__":
    # Ajusta la ruta a donde tengas tu archivo
    YAML_FILE = os.path.join(os.path.dirname(__file__), '../config/business_context.yaml')
    
    ctx = validate_structure(YAML_FILE)
    validate_physical_schema(ctx)