#!/usr/bin/env python3
"""
Test de conexión profesional para SQL Agent OSS
"""

import asyncio
import sys
import os
from contextlib import asynccontextmanager

# Configurar path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, '..', 'src')
sys.path.insert(0, src_dir)

from sqlalchemy import text
from sql_agent.database.connection import DatabaseManager

@asynccontextmanager
async def get_db_session():
    """Context manager para sesiones de base de datos"""
    engine = DatabaseManager.get_engine()
    async with engine.connect() as conn:
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        finally:
            await conn.close()

async def test_connection():
    """Test principal de conexión"""
    print("=" * 60)
    print("🧪 TEST DE CONEXIÓN A BASE DE DATOS")
    print("=" * 60)
    
    try:
        async with get_db_session() as session:
            # Test 1: Ping básico
            print("\n1. 🔍 Test de conectividad...")
            result = await session.execute(text("SELECT 1 as status, 'Conexión OK' as message"))
            row = result.fetchone()
            print(f"   ✅ {row.message} (Status: {row.status})")
            
            # Test 2: Versión de MySQL
            print("\n2. 📦 Información del servidor...")
            result = await session.execute(text("SELECT VERSION() as version"))
            version = result.fetchone().version
            print(f"   ✅ MySQL Version: {version}")
            
            # Test 3: Listado de tablas
            print("\n3. 📊 Análisis del esquema...")
            result = await session.execute(text("SHOW TABLES"))
            tables = [row[0] for row in result.fetchall()]
            
            print(f"   ✅ Tablas encontradas: {len(tables)}")
            
            # Mostrar categorías de tablas
            categories = {}
            for table in tables:
                prefix = table.split('_')[0] if '_' in table else 'other'
                categories[prefix] = categories.get(prefix, 0) + 1
            
            print("\n   📈 Distribución por prefijo:")
            for prefix, count in sorted(categories.items())[:10]:
                print(f"     - {prefix}: {count} tablas")
            
            # Test 4: Muestra de datos
            print("\n4. 📝 Muestra de datos (primeras 3 tablas):")
            for table_name in tables[:3]:
                try:
                    result = await session.execute(
                        text(f"SELECT COUNT(*) as count FROM `{table_name}`")
                    )
                    count = result.fetchone().count
                    print(f"   📄 {table_name}: {count:,} registros")
                    
                    # Muestra de columnas
                    result = await session.execute(
                        text(f"SHOW COLUMNS FROM `{table_name}`")
                    )
                    columns = [row[0] for row in result.fetchall()[:3]]
                    columns_str = ", ".join(columns)
                    if len(columns) > 3:
                        columns_str += "..."
                    print(f"     Columnas: [{columns_str}]")
                    
                except Exception as e:
                    print(f"   ⚠️  {table_name}: Error - {str(e)[:50]}...")
    
    except ImportError as e:
        print(f"\n❌ Error de importación: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Error de conexión: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("🎉 TODAS LAS PRUEBAS COMPLETADAS EXITOSAMENTE")
    print("=" * 60)
    return True

def main():
    """Punto de entrada principal"""
    try:
        success = asyncio.run(test_connection())
        return 0 if success else 1
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            # Error benigno al cerrar, ignorar
            return 0
        print(f"\n⚠️  Runtime error: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n\n⏹️  Test interrumpido por el usuario")
        return 130

if __name__ == "__main__":
    sys.exit(main())