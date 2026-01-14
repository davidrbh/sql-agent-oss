from sqlalchemy import inspect
# Eliminamos 'text' ya que no se usa en este archivo específico
from .connection import DatabaseManager

class SchemaExtractor:
    """
    Responsable de leer la estructura física de la base de datos.
    Ubicación: src/sql_agent/database/inspector.py
    """
    
    @staticmethod
    async def get_schema_info():
        """
        Extrae la lista de tablas y sus columnas usando SQLAlchemy Inspector.
        Retorna un diccionario estructurado.
        """
        engine = DatabaseManager.get_engine()
        
        # Inicializamos el diccionario vacío
        schema_info = {}
        
        # SQLAlchemy Async requiere 'run_sync' para operaciones de inspección (Inspector es síncrono)
        async with engine.connect() as conn:
            def sync_inspect(connection):
                inspector = inspect(connection)
                tables = inspector.get_table_names()
                
                data = {}
                for table in tables:
                    columns = inspector.get_columns(table)
                    # Simplificamos la salida para no saturar al LLM con metadatos innecesarios
                    data[table] = [
                        {
                            "name": col["name"],
                            "type": str(col["type"]),
                            "nullable": col["nullable"]
                        }
                        for col in columns
                    ]
                return data

            # Ejecutamos la función síncrona dentro del contexto asíncrono
            schema_info = await conn.run_sync(sync_inspect)
            
        return schema_info