from typing import TypedDict, Annotated, List, Dict, Any
import operator
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    """
    Representa la 'Memoria de Trabajo' del Agente durante una conversación.
    LangGraph pasará este objeto entre los nodos.
    """
    
    # Historial de chat: Lista de mensajes (Human, AI, Tool)
    # operator.add significa que cuando un nodo devuelve mensajes, se AGREGAN a la lista
    messages: Annotated[List[BaseMessage], operator.add]
