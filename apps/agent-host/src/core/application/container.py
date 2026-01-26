import os
from typing import Optional

from infra.config.loader import ConfigLoader
from infra.memory.postgres_checkpointer import PostgresCheckpointer
from infra.mcp.tool_provider import MCPToolProvider
from core.application.tool_manager import CompositeToolProvider

class Container:
    """
    Contenedor de Inyección de Dependencias para el ecosistema del agente.
    
    Esta clase gestiona el ciclo de vida de componentes de infraestructura compartidos 
    como pools de conexiones y clientes MCP, asegurando que se usen singletons donde sea apropiado.
    """

    _checkpointer: Optional[PostgresCheckpointer] = None
    _tool_provider: Optional[MCPToolProvider] = None

    @classmethod
    def get_checkpointer(cls) -> PostgresCheckpointer:
        """
        Devuelve el singleton global del checkpointer PostgreSQL.
        
        Requiere que la variable de entorno DB_URI esté configurada.
        """
        if cls._checkpointer is None:
            db_uri = os.getenv("DB_URI")
            if not db_uri:
                # Fallback para desarrollo local si no se proporciona
                db_uri = "postgresql://postgres:postgres@localhost:5432/agent_memory"
            
            cls._checkpointer = PostgresCheckpointer(db_uri)
        return cls._checkpointer

    @classmethod
    def get_tool_provider(cls) -> CompositeToolProvider:
        """
        Devuelve el singleton global del proveedor de herramientas compuesto.
        
        Agrega herramientas tanto de servidores MCP como de definiciones de API locales.
        """
        if cls._tool_provider is None:
            config_json = ConfigLoader.get_mcp_config()
            mcp_provider = MCPToolProvider(config_json)
            cls._tool_provider = CompositeToolProvider(mcp_provider)
        return cls._tool_provider

    @classmethod
    async def cleanup(cls):
        """Cierra ordenadamente todos los recursos compartidos."""
        if cls._checkpointer:
            await cls._checkpointer.close()
        if cls._tool_provider:
            await cls._tool_provider.close()
        print("🏛️ Recursos del contenedor limpiados.")