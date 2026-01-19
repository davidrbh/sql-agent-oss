import os
from typing import List
from langchain_openai import ChatOpenAI
from langchain_core.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import ToolMessage, SystemMessage, AIMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

# Imports para el Validador de SQL
from sqlglot import parse_one, exp

# Importa tu estado, ahora con el campo 'intent'
from agent_core.core.state import AgentState 

# --- NODO 1: CLASIFICADOR DE INTENCIÓN ---

def intent_classifier_node(state: AgentState):
    """
    Clasifica la intención de la pregunta del usuario para decidir qué
    conjunto de herramientas usar.
    """
    print("🚦 [Node: Intent Classifier] Clasificando intención...")
    
    # Usamos el LLM para una clasificación rápida
    prompt = ChatPromptTemplate.from_template(
        """Eres un router de intenciones. Clasifica la pregunta del usuario en una de estas tres categorías:
        
        - DATABASE: Si la pregunta implica consultar, contar, agregar o analizar datos de negocio como usuarios, compras, créditos, etc.
        - API: Si la pregunta es sobre el estado de un servicio, un endpoint, o una acción técnica no relacionada con datos de negocio.
        - GENERAL: Para saludos, preguntas conversacionales o cualquier otra cosa.

        Pregunta del usuario: "{question}"
        
        Responde con una sola palabra: DATABASE, API, o GENERAL.
        """
    )
    # Usamos un LLM simple y rápido para la clasificación
    llm = ChatOpenAI(model="deepseek-chat", temperature=0, api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    
    # Extraemos la última pregunta humana del historial
    question = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, HumanMessage):
            question = msg.content
            break

    chain = prompt | llm
    intent_raw = chain.invoke({"question": question}).content
    
    # Limpieza de la respuesta del LLM
    if "DATABASE" in intent_raw.upper():
        intent = "DATABASE"
    elif "API" in intent_raw.upper():
        intent = "API"
    else:
        intent = "GENERAL"
        
    print(f"   👉 Intención detectada: {intent}")
    return {"intent": intent}


# --- NODO 2: AGENTE DINÁMICO ---

def agent_node(state: AgentState, llm_with_tools: dict, system_prompt: str):
    """
    Nodo de agente dinámico. Enlaza y ejecuta el LLM con el conjunto
    de herramientas apropiado según la intención clasificada en el estado.
    """
    print(f"🧠 [Node: Agent] Actuando con la intención: {state['intent']}")
    
    # Selecciona el conjunto de herramientas correcto
    llm_runnable = llm_with_tools.get(state["intent"])
    
    # Si la intención es general o no tiene herramientas, usa el LLM base
    if not llm_runnable:
        llm_runnable = llm_with_tools["GENERAL"]

    messages = state["messages"]
    if not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=system_prompt)] + messages
        
    # Sanitización de mensajes (como antes)
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
    
    response = llm_runnable.invoke(sanitized_messages)
    return {"messages": [response]}


# --- NODO 3: GUARDIÁN DE SQL ---

def sql_validator_node(state: AgentState):
    """
    Nodo de validación de seguridad para consultas SQL. (Sin cambios)
    """
    print("🛡️ [Node: SQL Validator] Validando consulta SQL...")
    messages = state["messages"]
    last_message = messages[-1]

    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {"messages": []}

    for tool_call in last_message.tool_calls:
        if tool_call.get("name") == "query":
            sql_query = tool_call.get("args", {}).get("sql")
            if not sql_query:
                return {"messages": [ToolMessage(content="Error: Query SQL vacía.", tool_call_id=tool_call.get("id"), name="query")]}

            try:
                parsed_expression = parse_one(sql_query, read="mysql")
                forbidden_names = ["Drop", "Delete", "Insert", "Update", "Create", "Grant", "Revoke", "Alter", "AlterTable", "Truncate", "TruncateTable", "Command"]
                forbidden_nodes = [getattr(exp, name) for name in forbidden_names if hasattr(exp, name)]
                
                if parsed_expression and parsed_expression.find(*tuple(forbidden_nodes)):
                    found_node = parsed_expression.find(*tuple(forbidden_nodes))
                    error_msg = f"⛔ SEGURIDAD: Operación prohibida detectada ({found_node.key.upper()}). Solo se permite SELECT."
                    print(f"❌ {error_msg}")
                    return {"messages": [ToolMessage(content=error_msg, tool_call_id=tool_call.get("id"), name="query")]}
            except Exception as e:
                error_msg = f"⚠️ Error de Parsing SQL: {str(e)}. Consulta bloqueada por precaución."
                print(f"❌ {error_msg}")
                return {"messages": [ToolMessage(content=error_msg, tool_call_id=tool_call.get("id"), name="query")]}

    print("✅ Consulta(s) SQL validadas y seguras.")
    return {"messages": []}


# --- CONSTRUCTOR DEL GRAFO CON ROUTER ---

def build_graph(tools: List[BaseTool], system_prompt: str) -> StateGraph:
    """Construye el grafo principal del agente con un router de intención."""
    
    # 1. Separar herramientas por tipo
    sql_tools = [tool for tool in tools if tool.name == "query"]
    api_tools = [tool for tool in tools if tool.name != "query"]

    # 2. Configurar LLMs con herramientas específicas
    llm = ChatOpenAI(model="deepseek-chat", temperature=0, api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    
    llm_with_sql_tools = llm.bind_tools(sql_tools)
    llm_with_api_tools = llm.bind_tools(api_tools)
    
    # Diccionario de LLMs pre-configurados para el agente dinámico
    llm_with_tools_map = {
        "DATABASE": llm_with_sql_tools,
        "API": llm_with_api_tools,
        "GENERAL": llm # LLM base sin herramientas para conversaciones generales
    }

    # 3. Vincular el agente dinámico
    # Usamos una lambda para pasar los argumentos fijos (llm_map y prompt) al nodo
    dynamic_agent_node = lambda state: agent_node(state, llm_with_tools_map, system_prompt)
    
    # 4. Nodo de herramientas (sin cambios)
    tool_node = ToolNode(tools, handle_tool_errors=True)

    # 5. Definición del Flujo (Workflow) con Router
    workflow = StateGraph(AgentState)

    workflow.add_node("intent_classifier", intent_classifier_node)
    workflow.add_node("agent", dynamic_agent_node)
    workflow.add_node("sql_validator", sql_validator_node)
    workflow.add_node("tools", tool_node)

    workflow.set_entry_point("intent_classifier")

    # 6. Conexiones del Grafo
    workflow.add_edge("intent_classifier", "agent")

    # Después del agente, o vamos al validador (si hay tool calls) o terminamos
    def should_continue_from_agent(state: AgentState):
        last_message = state["messages"][-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "sql_validator"
        return END

    workflow.add_conditional_edges("agent", should_continue_from_agent, {"sql_validator": "sql_validator", END: END})
    
    # Después del validador, o vamos a ejecutar herramientas o volvemos al agente con el error
    def should_continue_from_validator(state: AgentState):
        if isinstance(state["messages"][-1], ToolMessage):
            return "agent" # Hubo un error de validación, el agente debe verlo
        return "tools" # Es seguro, ejecutar herramientas

    workflow.add_conditional_edges("sql_validator", should_continue_from_validator, {"agent": "agent", "tools": "tools"})
    
    workflow.add_edge("tools", "agent")

    return workflow.compile()
