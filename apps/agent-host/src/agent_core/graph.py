import os
from typing import List
from langchain_openai import ChatOpenAI
from langchain_core.tools import BaseTool
from langchain_core.messages import ToolMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

# Imports para el Validador de SQL
from sqlglot import parse_one, exp

# Importa tu estado
from agent_core.core.state import AgentState 

# --- NODO VALIDADOR DE SQL (VERSIÓN BLINDADA) ---

def sql_validator_node(state: AgentState):
    """
    Nodo de validación de seguridad para consultas SQL.
    Utiliza carga dinámica de atributos para evitar errores si sqlglot cambia de versión.
    """
    print("🛡️ [Node: SQL Validator] Validando consulta SQL...")
    messages = state["messages"]
    last_message = messages[-1]

    # Validación defensiva básica: Si no hay tool_calls, no hacemos nada.
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {"messages": []} # Retorno vacío explícito

    for tool_call in last_message.tool_calls:
        if tool_call.get("name") == "query":
            sql_query = tool_call.get("args", {}).get("sql")
            
            # 1. Validación de argumento existente
            if not sql_query:
                error_msg = f"Error: La herramienta 'query' (ID: {tool_call.get('id')}) fue llamada sin SQL."
                print(f"❌ {error_msg}")
                return {"messages": [ToolMessage(
                    content=error_msg,
                    tool_call_id=tool_call.get("id"),
                    name="query",
                    status="error"
                )]}

            try:
                # 2. Parsing con dialecto específico (MySQL)
                parsed_expression = parse_one(sql_query, read="mysql")
                
                # 3. CONSTRUCCIÓN DINÁMICA DE NODOS PROHIBIDOS (La solución al error)
                # Definimos los nombres como texto. Python buscará si existen en la librería.
                # Esto evita que el código explote si 'Alter' se llama 'AlterTable' en tu versión.
                forbidden_names = [
                    "Drop", "Delete", "Insert", "Update", "Create", "Grant", "Revoke",
                    "Alter", "AlterTable", "Truncate", "TruncateTable", "Command"
                ]
                
                forbidden_nodes = []
                for name in forbidden_names:
                    if hasattr(exp, name):
                        forbidden_nodes.append(getattr(exp, name))
                
                # Convertimos a tupla para usar en .find()
                forbidden_tuple = tuple(forbidden_nodes)
                
                # 4. Detección profunda
                if parsed_expression and parsed_expression.find(*forbidden_tuple):
                    # Recuperamos qué comando fue para el log
                    found_node = parsed_expression.find(*forbidden_tuple)
                    error_msg = (
                        f"⛔ SEGURIDAD: Operación prohibida detectada ({found_node.key.upper()}). "
                        "Solo se permite SELECT."
                    )
                    print(f"❌ {error_msg}")
                    
                    # Cortocircuito: Devolvemos el error inmediatamente al Agente
                    return {"messages": [ToolMessage(
                        content=error_msg,
                        tool_call_id=tool_call.get("id"),
                        name="query",
                        status="error"
                    )]}

            except Exception as e:
                # Si falla el parser, bloqueamos por seguridad.
                error_msg = f"⚠️ Error de Parsing SQL: {str(e)}. Consulta bloqueada por precaución."
                print(f"❌ {error_msg}")
                return {"messages": [ToolMessage(
                    content=error_msg,
                    tool_call_id=tool_call.get("id"),
                    name="query",
                    status="error"
                )]}

    print("✅ Consulta(s) SQL validadas y seguras. Procediendo a ejecución.")
    # Retornamos dict vacío para indicar que no hay nuevos mensajes (todo OK)
    return {"messages": []} 


# --- CONSTRUCTOR DEL GRAFO PRINCIPAL ---

def build_graph(tools: List[BaseTool], system_prompt: str) -> StateGraph:
    """Construye y compila el grafo principal del agente."""
    
    for tool in tools:
        tool.handle_tool_error = True

    llm = ChatOpenAI(
        model="deepseek-chat",
        temperature=0,
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com"
    )
    llm_with_tools = llm.bind_tools(tools)

    # NODO: Agente (El Cerebro)
    def agent_node(state: AgentState):
        messages = state["messages"]
        if not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + messages
            
        sanitized_messages = []
        for m in messages:
            if isinstance(m, ToolMessage) and isinstance(m.content, list):
                text_content = "".join([
                    block.get("text", "") for block in m.content 
                    if isinstance(block, dict) and block.get("type") == "text"
                ])
                new_m = ToolMessage(content=text_content, tool_call_id=m.tool_call_id, name=m.name)
                sanitized_messages.append(new_m)
            else:
                sanitized_messages.append(m)
        
        response = llm_with_tools.invoke(sanitized_messages)
        return {"messages": [response]}

    # NODO: Herramientas (El Brazo)
    tool_node = ToolNode(tools, handle_tool_errors=True)

    # DEFINICIÓN DEL FLUJO (WORKFLOW) CON BIFURCACIÓN DE SEGURIDAD
    workflow = StateGraph(AgentState)

    workflow.add_node("agent", agent_node)
    workflow.add_node("sql_validator", sql_validator_node)
    workflow.add_node("tools", tool_node)

    workflow.set_entry_point("agent")

    # Lógica condicional: Qué hacer después del 'agent_node'
    def should_continue_from_agent(state: AgentState):
        last_message = state["messages"][-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "sql_validator"
        return END

    # Lógica condicional: Qué hacer después del 'sql_validator'
    def should_continue_from_validator(state: AgentState):
        messages = state["messages"]
        last_message = messages[-1]
        
        # Si el último mensaje es un ToolMessage, significa que el validador
        # encontró un error y lo insertó. Debemos volver al agente.
        if isinstance(last_message, ToolMessage):
            return "agent"
            
        # Si el último mensaje sigue siendo el AIMessage original (porque el validador
        # devolvió lista vacía), procedemos a ejecutar las herramientas.
        return "tools"

    # CONEXIONES DEL GRAFO
    workflow.add_conditional_edges(
        "agent",
        should_continue_from_agent,
        {"sql_validator": "sql_validator", END: END}
    )
    
    workflow.add_conditional_edges(
        "sql_validator",
        should_continue_from_validator,
        {"agent": "agent", "tools": "tools"}
    )
    
    workflow.add_edge("tools", "agent")

    return workflow.compile()