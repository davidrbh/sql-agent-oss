import os
from typing import List, Optional
from langchain_openai import ChatOpenAI
from langchain_core.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import ToolMessage, SystemMessage, AIMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.base import BaseCheckpointSaver

# Imports para el Validador de SQL
from features.sql_analysis.tools.sql_guard import SQLGuard

# Importa tu estado, ahora con el campo 'intent'
from core.domain.state import AgentState

# --- NODO 1: CLASIFICADOR DE INTENCIÓN ---

def intent_classifier_node(state: AgentState):
    """
    Clasifica la intención de la pregunta del usuario para decidir qué
    conjunto de herramientas usar.
    """
    print("🚦 [Node: Intent Classifier] Clasificando intención...")
    
    # Usamos el LLM para una clasificación rápida
    # Tomamos los últimos 3 mensajes para dar contexto
    conversation_history = []
    for msg in state["messages"][-3:]: 
        role = "User" if isinstance(msg, HumanMessage) else "AI"
        content = str(msg.content)[:200] # Truncar por seguridad
        conversation_history.append(f"{role}: {content}")
    
    context_str = "\n".join(conversation_history)

    prompt = ChatPromptTemplate.from_template(
        """Eres un router de intenciones. Clasifica la ÚLTIMA interacción del usuario en una de estas categorías:
        
        - DATABASE: Consultar datos de negocio (usuarios, compras, créditos, etc.).
        - API: Consultar estado de servicios técnicos o endpoints externos.
        - GENERAL: Saludos, agradecimientos o charla casual.

        Historial reciente:
        {context}
        
        Responde con una sola palabra: DATABASE, API, o GENERAL.
        """
    )
    # Usamos un LLM simple y rápido para la clasificación
    llm = ChatOpenAI(model="deepseek-chat", temperature=0, api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    
    chain = prompt | llm
    intent_raw = chain.invoke({"context": context_str}).content
    
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

import re
import uuid

# --- PARSER DEEPSEEK (PATCH) ---
def parse_deepseek_xml(content: str):
    """
    Parsea llamadas a herramientas en formato XML raw de DeepSeek (DSML).
    Ejemplo: <|DSML|invoke name="query">...params...</|DSML|invoke>
    """
    tool_calls = []
    # Regex para bloques invoke
    invoke_pattern = r"<\|DSML\|invoke name=\"(.*?)\">(.*?)</\|DSML\|invoke>"
    invokes = re.findall(invoke_pattern, content, re.DOTALL)
    
    for name, body in invokes:
        args = {}
        # Regex para parámetros
        # Capturamos el nombre y el valor. Ignoramos atributos extra como string="true"
        param_pattern = r"<\|DSML\|parameter name=\"(.*?)\".*?>(.*?)</\|DSML\|parameter>"
        params = re.findall(param_pattern, body, re.DOTALL)
        
        for param_name, param_value in params:
            args[param_name] = param_value.strip()
            
        tool_calls.append({
            "id": str(uuid.uuid4()),
            "name": name,
            "args": args,
            "type": "tool_call"
        })
        
    return tool_calls

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
    
    # PATCH: DeepSeek XML Recovery
    # Si el modelo devolvió XML raw en el contenido en vez de tool_calls nativos
    if not response.tool_calls and "<|DSML|" in str(response.content):
        print("⚠️ [Agent] Detectado formato XML raw de DeepSeek. Intentando parsear...")
        parsed_tools = parse_deepseek_xml(response.content)
        if parsed_tools:
            print(f"✅ [Agent] Tool calls recuperados: {len(parsed_tools)}")
            response.tool_calls = parsed_tools
            # Limpiamos el content para que no se muestre como texto al usuario
            response.content = "" 
            
    return {"messages": [response]}


# --- NODO 3: GUARDIÁN DE SQL ---

def sql_validator_node(state: AgentState):
    """
    Nodo de seguridad que valida y normaliza las consultas SQL.
    
    Usa SQLGuard para realizar transpilación defensiva, eliminar comentarios 
    maliciosos y asegurar que las operaciones sean estrictamente de solo lectura.
    Si una consulta es insegura, devuelve un ToolMessage con el error para permitir 
    que el agente la corrija.
    """
    print("🛡️ [Node: SQL Validator] Validando y normalizando SQL...")
    messages = state["messages"]
    last_message = messages[-1]

    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {"messages": []}

    guard = SQLGuard(dialect="mysql")
    new_messages = []

    for tool_call in last_message.tool_calls:
        if tool_call.get("name") == "query":
            sql_query = tool_call.get("args", {}).get("sql")
            if not sql_query:
                new_messages.append(ToolMessage(
                    content="Error: Empty SQL query.", 
                    tool_call_id=tool_call.get("id"), 
                    name="query"
                ))
                continue

            is_safe, safe_sql, error_msg = guard.validate_and_transpile(sql_query)
            
            if not is_safe:
                print(f"❌ Violación de seguridad: {error_msg}")
                new_messages.append(ToolMessage(
                    content=f"⛔ ERROR DE SEGURIDAD: {error_msg}", 
                    tool_call_id=tool_call.get("id"), 
                    name="query"
                ))
            else:
                # Actualizar la llamada a la herramienta con el SQL transpilado (seguro)
                # Nota: En LangGraph, normalmente reemplazamos los args de tool_call en el estado
                # si queremos que el nodo tool_node posterior use la versión modificada.
                # Sin embargo, dado que no podemos mutar fácilmente AIMessage aquí,
                # solo lo registramos por ahora. En una v4 real, necesitaríamos una
                # actualización de estado más compleja o un ToolNode personalizado.
                print(f"✅ SQL validado y normalizado.")
                tool_call["args"]["sql"] = safe_sql # Intento de mutación

    return {"messages": new_messages}


# --- CONSTRUCTOR DEL GRAFO CON ROUTER ---

def build_graph(
    tools: List[BaseTool], 
    system_prompt: str, 
    checkpointer: Optional[BaseCheckpointSaver] = None
) -> StateGraph:
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
        
        # Si no hay tool calls, terminamos (es una respuesta de texto)
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            return END
        
        # Si hay tool calls, decidimos según la INTENCIÓN
        # Si la intención era DATABASE, pasamos por el filtro de seguridad
        if state["intent"] == "DATABASE":
            return "sql_validator"
        
        # Si es API o cualquier otra cosa, vamos directo a ejecutar (Skip Validator)
        return "tools"

    workflow.add_conditional_edges(
        "agent", 
        should_continue_from_agent, 
        {
            "sql_validator": "sql_validator",
            "tools": "tools",
            END: END
        }
    )
    
    # Después del validador, o vamos a ejecutar herramientas o volvemos al agente con el error
    def should_continue_from_validator(state: AgentState):
        if isinstance(state["messages"][-1], ToolMessage):
            return "agent" # Hubo un error de validación, el agente debe verlo
        return "tools" # Es seguro, ejecutar herramientas

    workflow.add_conditional_edges("sql_validator", should_continue_from_validator, {"agent": "agent", "tools": "tools"})
    
    workflow.add_edge("tools", "agent")

    return workflow.compile(checkpointer=checkpointer)
