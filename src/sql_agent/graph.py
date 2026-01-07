from langgraph.graph import StateGraph, END
from sql_agent.core.state import AgentState
from sql_agent.core.nodes import AgentNodes

def should_continue(state: AgentState):
    """
    Decide si avanzamos a la respuesta o volvemos a intentar el SQL.
    """
    last_result = state.get("sql_result", "")
    # Leemos la iteración actual. Si write_query devolvió N, aquí leemos N.
    current_iterations = state.get("iterations", 0)
    
    # Límite máximo de 3 intentos (0, 1, 2)
    MAX_RETRIES = 3

    if str(last_result).startswith("Error"):
        if current_iterations < MAX_RETRIES:
            print(f"🔄 [Graph] Error SQL detectado. Reintentando... (Intento {current_iterations}/{MAX_RETRIES})")
            return "retry"
        else:
            print(f"🛑 [Graph] Se alcanzaron los {MAX_RETRIES} intentos. Rindiéndose.")
            return "end"
    
    return "end"

def build_graph():
    nodes = AgentNodes()
    workflow = StateGraph(AgentState)
    
    # Nodos
    workflow.add_node("write_query", nodes.write_query)
    workflow.add_node("execute_query", nodes.execute_query)
    workflow.add_node("generate_answer", nodes.generate_answer)
    
    # Inicio
    workflow.set_entry_point("write_query")
    
    # Flujo Normal: Escribir -> Ejecutar
    workflow.add_edge("write_query", "execute_query")
    
    # Flujo Condicional: De Ejecutar -> ¿Reintentar o Responder?
    workflow.add_conditional_edges(
        "execute_query",
        should_continue,
        {
            "retry": "write_query",      # Vuelve a empezar corregido
            "end": "generate_answer"     # Todo bien, genera respuesta
        }
    )
    
    workflow.add_edge("generate_answer", END)
    
    return workflow.compile()