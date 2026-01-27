"""
Definición del estado del agente.

Este módulo define la estructura de datos que representa el estado interno
del agente durante una ejecución del grafo, incluyendo el historial de 
mensajes y la intención detectada.
"""

from typing import TypedDict, Annotated, List
import operator
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    """
    Representa la 'Memoria de Trabajo' del Agente durante una conversación.
    
    Attributes:
        messages: Lista de mensajes (Human, AI, Tool) que se acumulan mediante operator.add.
        intent: La intención clasificada del usuario (ej. 'DATABASE', 'API', 'GENERAL').
    """
    messages: Annotated[List[BaseMessage], operator.add]
    intent: str