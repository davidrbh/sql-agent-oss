from abc import ABC, abstractmethod
from typing import List, Any
from langchain_core.tools import BaseTool

class IToolProvider(ABC):
    """
    Puerto que define la interfaz para obtener herramientas de fuentes externas.
    
    Esta interfaz abstrae cómo se descubren y cargan las herramientas, permitiendo 
    que la lógica central del agente permanezca agnóstica al protocolo subyacente (ej. MCP).
    """

    @abstractmethod
    async def get_tools(self) -> List[BaseTool]:
        """
        Recupera una lista de herramientas ejecutables.

        Returns:
            List[BaseTool]: Una lista de objetos herramienta compatibles con LangChain.
        """
        pass

    @abstractmethod
    async def close(self):
        """
        Cierra cualquier conexión activa o recursos utilizados por el proveedor.
        """
        pass