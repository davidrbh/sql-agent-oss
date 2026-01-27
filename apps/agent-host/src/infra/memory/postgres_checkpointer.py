import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

logger = logging.getLogger(__name__)

class PostgresCheckpointer:
    """
    Gestiona la persistencia en PostgreSQL para los checkpoints de LangGraph.
    
    Esta clase proporciona un pool de conexiones seguro para hilos y un guardador 
    asíncrono para persistir el estado del agente, habilitando conversaciones de 
    múltiples turnos y tolerancia a fallos.
    """

    def __init__(self, conninfo: str, max_pool_size: int = 20):
        """
        Inicializa el checkpointer con una cadena de conexión.

        Args:
            conninfo: URI de conexión a PostgreSQL.
            max_pool_size: Número máximo de conexiones en el pool.
        """
        self.conninfo = conninfo
        # Configurar kwargs para autocommit=True es CRÍTICO para que .setup() funcione
        # y para evitar "CREATE INDEX CONCURRENTLY inside transaction block".
        self.pool = AsyncConnectionPool(
            conninfo=conninfo,
            max_size=max_pool_size,
            open=False,
            kwargs={"autocommit": True}
        )
        self._is_open = False

    @asynccontextmanager
    async def get_saver(self) -> AsyncGenerator[AsyncPostgresSaver, None]:
        """
        Proporciona una instancia de AsyncPostgresSaver usando el pool de conexiones.

        Yields:
            AsyncPostgresSaver: El checkpointer compatible con LangGraph.
        """
        if not self._is_open:
            await self.pool.open()
            self._is_open = True
            
        saver = AsyncPostgresSaver(self.pool)
        # Asegurar que el esquema esté configurado (Seguro para llamadas concurrentes en producción)
        # En entornos estrictamente regulados, esto podría manejarse vía Alembic.
        await saver.setup()
        
        try:
            yield saver
        finally:
            # El saver no necesita cierre explícito si usa un pool,
            # pero mantenemos la estructura para futuras extensiones.
            pass

    async def close(self):
        """Cierra el pool de conexiones."""
        if self._is_open:
            await self.pool.close()
            self._is_open = False
            logger.info("Pool de conexiones Postgres cerrado.")