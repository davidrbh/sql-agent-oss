"""
Orquestador del flujo cognitivo (LangGraph).

Este módulo define la máquina de estados (StateGraph) que gobierna el comportamiento
del agente, incluyendo la clasificación de intención, la invocación del LLM y
la ejecución segura de herramientas mediante validación AST.
"""

import os
import re
import uuid
import logging
from typing import List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import ToolMessage, SystemMessage, AIMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from core.domain.state import AgentState
from features.sql_analysis.tools.sql_guard import SQLGuard

logger = logging.getLogger(__name__)


def intent_classifier_node(state: AgentState) -> dict:
    """
    Clasifica la intención del usuario para decidir qué conjunto de herramientas usar.

    Args:
        state: El estado actual del agente.

    Returns:
        dict: Actualización del estado con la intención detectada.
    """
    conversation_history = []
    for msg in state["messages"][-3:]: 
        role = "User" if isinstance(msg, HumanMessage) else "AI"
        content = str(msg.content)[:200]
        conversation_history.append(f"{role}: {content}")
    
    context_str = "\n".join(conversation_history)

    prompt = ChatPromptTemplate.from_template(
        """Eres un clasificador de intenciones experto. Analiza la ÚLTIMA pregunta del usuario y clasifícala en:
        - DATABASE: Consultas de datos de negocio, conteos, tablas o esquemas (ej: "cuantos...", "que tablas...", "quien es...").
        - API: Consultas técnicas sobre capacidades del sistema, endpoints disponibles, estado de servicios o llamadas HTTP (ej: "¿qué endpoints hay?", "¿puedes llamar a la API?").
        - GENERAL: Saludos o charla casual.
        
        Historial:
        {context}
        
        Responde ÚNICAMENTE con una palabra: DATABASE, API, o GENERAL.
        """
    )
    
    llm = ChatOpenAI(
        model="deepseek-chat", 
        temperature=0, 
        api_key=os.getenv("DEEPSEEK_API_KEY"), 
        base_url="https://api.deepseek.com"
    )
    
    chain = prompt | llm
    intent_raw = chain.invoke({"context": context_str}).content.upper()
    
    intent = "GENERAL"
    if "DATABASE" in intent_raw:
        intent = "DATABASE"
    elif "API" in intent_raw:
        intent = "API"
        
    logger.info(f"Intención detectada: {intent}")
    return {"intent": intent}


def parse_deepseek_xml(content: str) -> list:
    """
    Parsea llamadas a herramientas en formato XML de DeepSeek (DSML).

    Args:
        content: Contenido textual generado por el LLM.

    Returns:
        list: Lista de diccionarios con las llamadas a herramientas parseadas.
    """
    tool_calls = []
    invoke_pattern = r"<\|DSML\|invoke name=\"(.*?)\">(.*?)</\|DSML\|invoke>"
    invokes = re.findall(invoke_pattern, content, re.DOTALL)
    
    for name, body in invokes:
        args = {}
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


def agent_node(state: AgentState, llm_with_tools: dict, system_prompt: str) -> dict:
    """
    Nodo de agente que invoca al LLM con refuerzo de instrucciones para herramientas.

    Args:
        state: El estado actual del agente.
        llm_with_tools: Mapeo de modelos con herramientas vinculadas.
        system_prompt: Instrucciones base del sistema.

    Returns:
        dict: Actualización del estado con el nuevo mensaje del asistente.
    """
    llm_runnable = llm_with_tools.get(state["intent"], llm_with_tools["GENERAL"])

    current_prompt = system_prompt
    if state["intent"] == "DATABASE":
        current_prompt += (
            "\n\nIMPORTANTE: Para responder preguntas sobre datos, DEBES llamar a la herramienta 'query'. "
            "No intentes responder solo con texto si necesitas datos de la base de datos."
        )

    messages = state["messages"]
    if not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=current_prompt)] + messages
    else:
        messages[0] = SystemMessage(content=current_prompt)
        
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
    
    if not response.tool_calls and "<|DSML|" in str(response.content):
        parsed_tools = parse_deepseek_xml(response.content)
        if parsed_tools:
            response.tool_calls = parsed_tools
            response.content = "" 
            
    return {"messages": [response]}


def build_graph(
    tools: List[BaseTool], 
    system_prompt: str, 
    checkpointer: Optional[BaseCheckpointSaver] = None
) -> StateGraph:
    """
    Construye y compila el grafo de ejecución del agente.

    Args:
        tools: Lista de herramientas disponibles.
        system_prompt: Instrucciones del sistema.
        checkpointer: Motor de persistencia opcional.

    Returns:
        StateGraph: El grafo compilado listo para ser invocado.
    """
    tool_map = {tool.name: tool for tool in tools}
    guard = SQLGuard(dialect="mysql")
    
    llm = ChatOpenAI(
        model="deepseek-chat", 
        temperature=0, 
        api_key=os.getenv("DEEPSEEK_API_KEY"), 
        base_url="https://api.deepseek.com"
    )
    
    sql_tools = [t for t in tools if t.name == "query"]
    api_tools = [t for t in tools if t.name != "query"]

    llm_with_tools_map = {
        "DATABASE": llm.bind_tools(sql_tools),
        "API": llm.bind_tools(api_tools),
        "GENERAL": llm 
    }

    async def validated_tool_node(state: AgentState):
        """Maneja la ejecución de herramientas con validación previa de seguridad SQL."""
        last_message = state["messages"][-1]
        results = []
        
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            return {"messages": []}

        for tool_call in last_message.tool_calls:
            name = tool_call["name"]
            args = tool_call["args"]
            tid = tool_call["id"]
            
            logger.info(f"Ejecutando herramienta: {name}")
            
            if name == "query":
                sql = args.get("sql", "")
                is_safe, safe_sql, error_msg = guard.validate_and_transpile(sql)
                
                if not is_safe:
                    logger.warning(f"Consulta SQL bloqueada: {error_msg}")
                    results.append(ToolMessage(
                        content=f"⛔ ERROR DE SEGURIDAD: {error_msg}", 
                        tool_call_id=tid, 
                        name=name
                    ))
                    continue
                args["sql"] = safe_sql or sql

            tool = tool_map.get(name)
            if tool:
                try:
                    output = await tool.ainvoke(args)
                    results.append(ToolMessage(content=str(output), tool_call_id=tid, name=name))
                except Exception as e:
                    logger.error(f"Error en herramienta {name}: {str(e)}")
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
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    workflow.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")

    return workflow.compile(checkpointer=checkpointer)
