import json
from sql_agent.utils.mcp_client import mcp_manager
# from sqlalchemy import inspect # Removed
# from .connection import DatabaseManager # Removed

class SchemaExtractor:
    """
    Responsable de leer la estructura física de la base de datos.
    Ubicación: src/sql_agent/database/inspector.py
    """
    
    @staticmethod
    async def get_schema_info():
        """
        Extrae la lista de tablas y sus columnas usando MCP Sidecar.
        Retorna un diccionario estructurado.
        """
        print("🔍 [SchemaExtractor] Fetching schema via MCP...")
        session = await mcp_manager.get_session()
        
        # 1. Listar Tablas
        # Sidecar 'list_tables' -> content: JSON string of [{"Tables_in_xyz": "tablename"}]
        result = await session.call_tool("list_tables", arguments={})
        text_content = "".join([c.text for c in result.content if c.type == 'text'])
        
        try:
            tables_raw = json.loads(text_content)
            tables = []
            for row in tables_raw:
                # Extraer el primer valor (nombre de la tabla)
                tables.extend(list(row.values()))
        except Exception as e:
            print(f"❌ Error parsing tables list: {e}")
            return {}
            
        schema_info = {}
        
        # 2. Detalar cada tabla
        for table in tables:
            try:
                desc_result = await session.call_tool("describe_table", arguments={"tableName": table})
                desc_text = "".join([c.text for c in desc_result.content if c.type == 'text'])
                columns_data = json.loads(desc_text)
                
                # Mapear formato DESCRIBE normalizado
                schema_info[table] = [
                    {
                        "name": col.get("Field") or col.get("name"),
                        "type": col.get("Type") or col.get("type"),
                        "nullable": (col.get("Null") == "YES") or (col.get("nullable") == True)
                    }
                    for col in columns_data
                ]
            except Exception as e:
                print(f"⚠️ Error describing table {table}: {e}")
                
        return schema_info