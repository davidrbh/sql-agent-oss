from langgraph.graph import StateGraph, END
from sql_agent.core.state import AgentState
from sql_agent.core.nodes import AgentNodes

def build_graph():
    """
    Construye el Grafo de Ejecución (El Cerebro del Agente).
    Define el flujo: Write -> Execute -> Answer.
    """
    
    # 1. Inicializamos las Neuronas (Nodos)
    nodes = AgentNodes()
    
    # 2. Definimos el Grafo con nuestro Estado (Memoria)
    workflow = StateGraph(AgentState)
    
    # 3. Agregamos los Nodos al Grafo
    workflow.add_node("write_query", nodes.write_query)
    workflow.add_node("execute_query", nodes.execute_query)
    workflow.add_node("generate_answer", nodes.generate_answer)
    
    # 4. Conectamos los Nodos (Los Cables)
    # Definimos el punto de entrada
    workflow.set_entry_point("write_query")
    
    # Flujo lineal: write -> execute -> answer -> FIN
    workflow.add_edge("write_query", "execute_query")
    workflow.add_edge("execute_query", "generate_answer")
    workflow.add_edge("generate_answer", END)
    
    # 5. Compilamos el grafo (Lo convertimos en ejecutable)
    app = workflow.compile()
    
    return app
