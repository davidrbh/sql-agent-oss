from langgraph.graph import StateGraph, END
from sql_agent.core.state import AgentState
from sql_agent.core.nodes import AgentNodes

# --- Lógica Condicional ---
def route_intent(state: AgentState):
    """Router Principal"""
    intent = state.get("intent", "GENERAL")
    if intent == "DATABASE": return "write_query"
    if intent == "API": return "call_api"
    return "generate_answer"

def check_sql_retry(state: AgentState):
    """Router de Reintento SQL"""
    result = state.get("sql_result", "")
    iters = state.get("iterations", 0)
    if "Error" in str(result) and iters < 3:
        return "retry"
    return "done"

# --- Construcción ---
def build_graph():
    nodes = AgentNodes()
    workflow = StateGraph(AgentState)
    
    # 1. Añadir Nodos
    workflow.add_node("router", nodes.classify_intent)
    workflow.add_node("write_query", nodes.write_query)
    workflow.add_node("execute_query", nodes.execute_query)
    workflow.add_node("call_api", nodes.run_api_tool)
    workflow.add_node("generate_answer", nodes.generate_answer)
    
    # 2. Punto de Entrada
    workflow.set_entry_point("router")
    
    # 3. Conexiones del Router (La "Y")
    workflow.add_conditional_edges(
        "router",
        route_intent,
        {
            "write_query": "write_query",
            "call_api": "call_api",
            "generate_answer": "generate_answer"
        }
    )
    
    # 4. Rama SQL
    workflow.add_edge("write_query", "execute_query")
    workflow.add_conditional_edges(
        "execute_query",
        check_sql_retry,
        {
            "retry": "write_query",
            "done": "generate_answer"
        }
    )
    
    # 5. Rama API
    workflow.add_edge("call_api", "generate_answer")
    
    # 6. Salida
    workflow.add_edge("generate_answer", END)
    
    return workflow.compile()