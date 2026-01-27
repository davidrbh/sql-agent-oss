import os
import re
import uuid
from typing import List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import ToolMessage, SystemMessage, AIMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from core.domain.state import AgentState
from features.sql_analysis.tools.sql_guard import SQLGuard

# --- NODO 1: CLASIFICADOR DE INTENCIÓN ---

def intent_classifier_node(state: AgentState):
    """Clasifica la intención del usuario."""
    
    conversation_history = []
    for msg in state["messages"][-3:]:
        role = "User" if isinstance(msg, HumanMessage) else "AI"
        content = str(msg.content)[:200]
        conversation_history.append(f"{role}: {content}")
    
    context_str = "\n".join(conversation_history)

    prompt = ChatPromptTemplate.from_template(
        """Eres un clasificador de intenciones experto. Analiza la ÚLTIMA pregunta del usuario y clasifícala en:
        - DATABASE: Consultas de datos de negocio, conteos, tablas o esquemas (ej: \"cuantos...\", \"que tablas...\", \"quien es...\").
        - API: Consultas técnicas de estado de servicios.
        - GENERAL: Saludos o charla casual.
        
        Historial:
        {context}
        
        Responde ÚNICAMENTE: DATABASE, API, o GENERAL.
        """
    )
    llm = ChatOpenAI(model="deepseek-chat", temperature=0, api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    
    chain = prompt | llm
    intent_raw = chain.invoke({"context": context_str}).content.upper()
    
    intent = "GENERAL"
    if "DATABASE" in intent_raw: intent = "DATABASE"
    elif "API" in intent_raw: intent = "API"
        
    return {"intent": intent}


# --- NODO 2: AGENTE DINÁMICO ---

def parse_deepseek_xml(content: str):
    """Parsea llamadas a herramientas en formato XML de DeepSeek."""
    tool_calls = []
    invoke_pattern = r"<\|DSML\|invoke name=\"(.*?)\">(.*?)</\|DSML\|invoke>"
    invokes = re.findall(invoke_pattern, content, re.DOTALL)
    
    for name, body in invokes:
        args = {}
        param_pattern = r"<\|DSML\|parameter name=\"(.*?)\" .*?>(.*?)</\|DSML\|parameter>"
        params = re.findall(param_pattern, body, re.DOTALL)
        for param_name, param_value in params:
            args[param_name] = param_value.strip()
            
        tool_calls.append({"id": str(uuid.uuid4()), "name": name, "args": args, "type": "tool_call"})
    return tool_calls

def agent_node(state: AgentState, llm_with_tools: dict, system_prompt: str):
    """Invoca al LLM con refuerzo de instrucciones para el uso de herramientas."""
    
    llm_runnable = llm_with_tools.get(state["intent"], llm_with_tools["GENERAL"])

    # Refuerzo para DATABASE: Forzar el uso de la herramienta 'query'
    if state["intent"] == "DATABASE":
        system_prompt += "\n\nIMPORTANTE: Para responder preguntas sobre datos, DEBES llamar a la herramienta 'query'. No intentes responder solo con texto si necesitas datos de la base de datos."

    messages = state["messages"]
    if not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=system_prompt)] + messages
    else:
        messages[0] = SystemMessage(content=system_prompt)
        
    sanitized_messages = []
    for m in messages:
        if isinstance(m, ToolMessage) and isinstance(m.content, list):
            text = "".join([b.get("text", "") for b in m.content if b.get("type") == "text"])
            sanitized_messages.append(ToolMessage(content=text, tool_call_id=m.tool_call_id, name=m.name))
        else:
            sanitized_messages.append(m)
    
    response = llm_runnable.invoke(sanitized_messages)
    
    if not response.tool_calls and "<|DSML|" in str(response.content):
        parsed = parse_deepseek_xml(response.content)
        if parsed:
            response.tool_calls = parsed
            response.content = "" 
            
    return {"messages": [response]}


# --- CONSTRUCTOR DEL GRAFO ---

def build_graph(
    tools: List[BaseTool], 
    system_prompt: str, 
    checkpointer: Optional[BaseCheckpointSaver] = None
) -> StateGraph:
    """Construye el grafo con validación integrada en el nodo de herramientas."""
    
    tool_map = {tool.name: tool for tool in tools}
    guard = SQLGuard(dialect="mysql")
    llm = ChatOpenAI(model="deepseek-chat", temperature=0, api_key=os.getenv("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
    
    sql_tools = [t for t in tools if t.name == "query"]
    api_tools = [t for t in tools if t.name != "query"]

    llm_with_tools_map = {
        "DATABASE": llm.bind_tools(sql_tools),
        "API": llm.bind_tools(api_tools),
        "GENERAL": llm 
    }

    # Nodo de Herramientas con Seguridad (ASYNC)
    async def validated_tool_node(state: AgentState):
        last_message = state["messages"][-1]
        results = []
        
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            return {"messages": []}

        for tool_call in last_message.tool_calls:
            name = tool_call["name"]
            args = tool_call["args"]
            tid = tool_call["id"]
            
            if name == "query":
                sql = args.get("sql", "")
                is_safe, safe_sql, error_msg = guard.validate_and_transpile(sql)
                if not is_safe:
                    results.append(ToolMessage(content=f"⛔ ERROR DE SEGURIDAD: {error_msg}", tool_call_id=tid, name=name))
                    continue
                args["sql"] = safe_sql or sql

            tool = tool_map.get(name)
            if tool:
                try:
                    output = await tool.ainvoke(args)
                    results.append(ToolMessage(content=str(output), tool_call_id=tid, name=name))
                except Exception as e:
                    results.append(ToolMessage(content=f"Error: {str(e)}", tool_call_id=tid, name=name))
            else:
                results.append(ToolMessage(content=f"Error: Tool {name} not found", tool_call_id=tid, name=name))
        
        return {"messages": results}

    workflow = StateGraph(AgentState)
    workflow.add_node("intent_classifier", intent_classifier_node)
    workflow.add_node("agent", lambda s: agent_node(state=s, llm_with_tools=llm_with_tools_map, system_prompt=system_prompt))
    workflow.add_node("tools", validated_tool_node)

    workflow.set_entry_point("intent_classifier")
    workflow.add_edge("intent_classifier", "agent")

    def should_continue(state: AgentState):
        last = state["messages"][-1]
        return "tools" if isinstance(last, AIMessage) and last.tool_calls else END

    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")

    return workflow.compile(checkpointer=checkpointer)