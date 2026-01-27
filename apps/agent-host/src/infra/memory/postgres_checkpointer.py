"""
Módulo de persistencia en PostgreSQL.

Este módulo implementa el checkpointer para LangGraph utilizando PostgreSQL,
permitiendo que el estado del agente sea persistente y transaccional mediante
el uso de pooling de conexiones asíncronas.
"""

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
    
    Esta clase proporciona un pool de conexiones seguro y un guardador asíncrono 
    para persistir el estado del agente, habilitando conversaciones multi-turno
    y tolerancia a fallos.
    """

    def __init__(self, conninfo: str, max_pool_size: int = 20):
        """
        Inicializa el checkpointer con una cadena de conexión.

        Args:
            conninfo: URI de conexión a PostgreSQL.
            max_pool_size: Número máximo de conexiones simultáneas en el pool.
        """
        self.conninfo = conninfo
        # autocommit=True es requerido por .setup() para crear tablas e índices.
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

        Este gestor de contexto asegura que el pool esté abierto y que el esquema
        de la base de datos esté inicializado antes de devolver el saver.

        Yields:
            AsyncPostgresSaver: El motor de persistencia para LangGraph.
        """
        if not self._is_open:
            await self.pool.open()
            self._is_open = True
            
        saver = AsyncPostgresSaver(self.pool)
        await saver.setup()
        
        try:
            yield saver
        finally:
            pass

    async def close(self):
        """
        Cierra el pool de conexiones y libera los recursos.
        """
        if self._is_open:
            await self.pool.close()
            self._is_open = False
            logger.info("Pool de conexiones Postgres cerrado.")
