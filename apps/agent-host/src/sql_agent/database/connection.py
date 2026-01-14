import os
import asyncio
import atexit
import warnings
from typing import Optional, List, Dict, Any
from urllib.parse import quote_plus
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from sqlalchemy import text

# Cargar configuración del entorno
load_dotenv()

# Suprimir warnings específicos
warnings.filterwarnings("ignore", message="Event loop is closed")

def get_database_url(show_password: bool = False) -> str:
    """
    Construye la URL de conexión para SQLAlchemy.
    
    Args:
        show_password: Si es True, incluye la contraseña en la URL
    """
    driver = os.getenv("DB_DRIVER", "aiomysql")
    user = os.getenv("DB_USER", "")
    password = os.getenv("DB_PASSWORD", "")
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "3306")
    db_name = os.getenv("DB_NAME", "")
    
    # Codificar caracteres especiales
    safe_password = quote_plus(password) if password else ""
    
    # Construir URL
    if show_password and password:
        url = f"mysql+{driver}://{user}:{safe_password}@{host}:{port}/{db_name}"
    else:
        url = f"mysql+{driver}://{user}:{'***' if password else ''}@{host}:{port}/{db_name}"
    
    # Solo parámetros compatibles con aiomysql
    params = []
    params.append("charset=utf8mb4")
    
    if connect_timeout := os.getenv("DB_CONNECT_TIMEOUT"):
        params.append(f"connect_timeout={connect_timeout}")
    
    if os.getenv("DB_USE_SSL", "false").lower() == "true":
        params.append("ssl=true")
    
    if params:
        url += "?" + "&".join(params)
    
    return url

def get_safe_database_url() -> str:
    """Devuelve la URL segura (sin password visible)"""
    return get_database_url(show_password=False)

class DatabaseManager:
    """
    Gestor de conexiones - Versión corregida
    """
    _engine: Optional[AsyncEngine] = None
    _cleanup_registered: bool = False
    
    @classmethod
    def get_engine(cls) -> AsyncEngine:
        """Obtiene o crea el motor de base de datos singleton."""
        if cls._engine is None:
            # Usar URL CON password para la conexión real
            url_with_password = get_database_url(show_password=True)
            
            # Configuración del engine
            cls._engine = create_async_engine(
                url_with_password,
                echo=os.getenv("SQL_ECHO", "false").lower() == "true",
                pool_pre_ping=True,
                pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
                max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
                pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "3600")),
                pool_timeout=30,
                pool_use_lifo=True,
                pool_reset_on_return=True,
            )
            
            # Registrar cleanup
            cls._register_cleanup()
            
            # Mostrar URL SEGURA (sin password)
            safe_url = get_safe_database_url()
            print(f"✅ Motor de base de datos inicializado")
            print(f"   📍 {safe_url}")
        
        return cls._engine
    
    @classmethod
    def _register_cleanup(cls):
        """Registra función de cleanup."""
        if not cls._cleanup_registered:
            atexit.register(cls._cleanup_sync)
            cls._cleanup_registered = True
    
    @classmethod
    def _cleanup_sync(cls):
        """Cleanup seguro al cerrar la aplicación."""
        if cls._engine is not None:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def dispose():
                    await cls._engine.dispose()
                    cls._engine = None
                
                loop.run_until_complete(dispose())
                loop.close()
                print("✅ Motor de base de datos cerrado (cleanup)")
            except Exception as e:
                # Ignorar errores en cleanup
                pass
    
    @classmethod
    async def close(cls):
        """Cierra el motor de manera explícita y segura."""
        if cls._engine is not None:
            await cls._engine.dispose()
            cls._engine = None
            print("✅ Motor de base de datos cerrado manualmente")
    
    @classmethod
    async def ping(cls) -> bool:
        """Verifica que la base de datos está accesible."""
        try:
            async with cls.get_engine().connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                return bool(result.scalar())
        except Exception as e:
            print(f"❌ Error en ping: {e}")
            return False
    
    @classmethod 
    async def get_tables(cls) -> List[str]:
        """Obtiene la lista de todas las tablas."""
        async with cls.get_engine().connect() as conn:
            result = await conn.execute(text("SHOW TABLES"))
            return [row[0] for row in result.fetchall()]
    
    @classmethod
    async def get_table_info(cls, table_name: str) -> Dict[str, Any]:
        """Obtiene información de una tabla."""
        async with cls.get_engine().connect() as conn:
            # Columnas
            query = text("""
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE() 
                AND TABLE_NAME = :table_name
                ORDER BY ORDINAL_POSITION
            """)
            result = await conn.execute(query, {"table_name": table_name})
            columns = result.fetchall()
            
            # Contar filas
            count_query = text(f"SELECT COUNT(*) FROM `{table_name}`")
            result = await conn.execute(count_query)
            row_count = result.scalar()
            
            return {
                "table_name": table_name,
                "row_count": row_count,
                "columns": [
                    {
                        "name": col[0],
                        "type": col[1],
                        "nullable": col[2] == "YES",
                        "key": col[3] or ""
                    }
                    for col in columns
                ]
            }