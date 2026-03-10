'''
Orquestador del flujo cognitivo (LangGraph).

Este módulo define la máquina de estados (StateGraph) que gobierna el comportamiento
del agente, incluyendo la clasificación de intención, la invocación del LLM y
la ejecución segura de herramientas mediante validación AST.
'''

import os
import re
import uuid
import logging
import asyncio
import traceback
from typing import List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import ToolMessage, SystemMessage, AIMessage, HumanMessage, BaseMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from core.domain.state import AgentState
from features.sql_analysis.tools.sql_guard import SQLGuard

logger = logging.getLogger(__name__) 


def intent_classifier_node(state: AgentState) -> dict:
    '''Clasifica la intención del usuario para optimizar el set de herramientas.'''
    conversation_history = []
    # Tomamos los últimos mensajes relevantes para contexto
    for msg in state["messages"][-5:]:
        role = "User" if isinstance(msg, HumanMessage) else "AI"
        content = str(msg.content)[:200]
        conversation_history.append(f"{role}: {content}")
    
    context_str = "\n".join(conversation_history)

    prompt = ChatPromptTemplate.from_template(
        """Eres un clasificador de intenciones experto. Analiza la conversación y clasifica la ÚLTIMA petición en:
        - DATABASE: Consultas de datos de negocio, conteos, tablas o esquemas.
        - API: Consultas técnicas sobre capacidades generales del sistema o endpoints genéricos.
        - CAMPAIGNS: Creación, lista, previsualización, edición o borrado de campañas de notificación (Lysto).
        - GENERAL: Saludos o charla casual.
        
        Historial:
        {context}
        
        Responde ÚNICAMENTE con una palabra: DATABASE, API, CAMPAIGNS o GENERAL.
        """
    )
    
    llm = ChatOpenAI(
        model="deepseek-chat", 
        temperature=0, 
        api_key=os.getenv("DEEPSEEK_API_KEY"), 
        base_url="https://api.deepseek.com"
    )
    
    intent = "GENERAL"
    try:
        chain = prompt | llm
        intent_raw = chain.invoke({"context": context_str}).content.upper()
        if "DATABASE" in intent_raw: intent = "DATABASE"
        elif "CAMPAIGNS" in intent_raw: intent = "CAMPAIGNS"
        elif "API" in intent_raw: intent = "API"
    except Exception as e:
        logger.error(f"Error en clasificación de intención: {e}")
        
    logger.info(f"Intención detectada: {intent}")
    return {"intent": intent}


def parse_deepseek_xml(content: str) -> list:
    '''Parsea llamadas a herramientas en formato XML raw de DeepSeek (robusto a pipes).'''
    tool_calls = []
    # Soporta tanto | como ｜ (full-width)
    invoke_pattern = r"<[|｜]DSML[|｜]invoke name=\"(.*?)\">(.*?)</[|｜]DSML[|｜]invoke>"
    invokes = re.findall(invoke_pattern, content, re.DOTALL)
    
    for name, body in invokes:
        args = {}
        param_pattern = r"<[|｜]DSML[|｜]parameter name=\"(.*?)\".*?>(.*?)</[|｜]DSML[|｜]parameter>"
        params = re.findall(param_pattern, body, re.DOTALL)
        for param_name, param_value in params:
            args[param_name] = param_value.strip()
            
        tool_calls.append({
            "id": f"call_{uuid.uuid4().hex[:12]}",
            "name": name,
            "args": args,
            "type": "tool_call"
        })
    return tool_calls


def sanitize_history_for_llm(messages: List[BaseMessage]) -> List[BaseMessage]:
    '''
    Asegura que el historial de mensajes sea válido para la API de OpenAI/DeepSeek.
    Elimina tool_calls que no tengan su correspondiente ToolMessage.
    '''
    sanitized = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        
        if isinstance(msg, AIMessage) and msg.tool_calls:
            has_tool_response = False
            if i + 1 < len(messages) and isinstance(messages[i+1], ToolMessage):
                has_tool_response = True
            
            if not has_tool_response:
                logger.warning(f"Sanitizando AIMessage con tool_calls sin respuesta (ID: {msg.id})")
                new_msg = AIMessage(content=msg.content or "Procesando...", id=msg.id)
                sanitized.append(new_msg)
            else:
                sanitized.append(msg)
        else:
            if isinstance(msg, ToolMessage) and isinstance(msg.content, list):
                text = "".join([b.get("text", "") for b in msg.content if isinstance(b, dict) and b.get("type") == "text"])
                sanitized.append(ToolMessage(content=text, tool_call_id=msg.tool_call_id, name=msg.name))
            else:
                sanitized.append(msg)
        i += 1
    return sanitized


def agent_node(state: AgentState, llm_with_tools: dict, system_prompt: str) -> dict:
    '''Invoca al LLM con refuerzo de instrucciones y sanitización de historial.'''
    llm_runnable = llm_with_tools.get(state["intent"], llm_with_tools["GENERAL"])

    # Optimizamos para Prompt Caching: El grueso del prompt (system_prompt) va SIEMPRE al inicio.
    # Las instrucciones dinámicas de intención se añaden al final del mensaje de sistema para no romper el prefijo.
    full_system_content = system_prompt
    if state["intent"] == "DATABASE":
        full_system_content += (
            "\n\n[INSTRUCCIÓN DINÁMICA]: Estás en modo DATABASE. Prioriza el uso de 'query'."
        )
    elif state["intent"] == "API":
        full_system_content += (
            "\n\n[INSTRUCCIÓN DINÁMICA]: Estás en modo API. Usa las herramientas de integración disponibles."
        )
    elif state["intent"] == "CAMPAIGNS":
        full_system_content += (
            "\n\n[INSTRUCCIÓN DINÁMICA]: Estás en modo CAMPAIGNS. Usa las herramientas de Lysto para gestionar campañas de notificación."
        )

    messages = state["messages"]
    # Reemplazamos o insertamos el mensaje de sistema optimizado
    if messages and isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=full_system_content)] + messages[1:]
    else:
        messages = [SystemMessage(content=full_system_content)] + messages
        
    sanitized_messages = sanitize_history_for_llm(messages)
    
    try:
        response = llm_runnable.invoke(sanitized_messages)
    except Exception as e:
        logger.error(f"Error invocando LLM: {e}")
        return {"messages": [AIMessage(content="Lo siento, he tenido un error técnico al procesar tu solicitud.")]}
    
    # Detección y limpieza de DSML (soporta pipes normales y anchos)
    content_str = str(response.content)
    if not response.tool_calls and ("<|DSML|" in content_str or "<｜DSML｜" in content_str):
        parsed = parse_deepseek_xml(content_str)
        if parsed:
            response.tool_calls = parsed
            # Limpiamos el bloque completo de function_calls para que no se vea en la UI.
            # Eliminamos desde el tag <｜DSML｜function_calls> hasta </｜DSML｜function_calls>
            clean_content = re.sub(
                r"<[|｜]DSML[|｜]function_calls>.*?</[|｜]DSML[|｜]function_calls>",
                "",
                content_str,
                flags=re.DOTALL
            )
            # Por si acaso quedan tags sueltos sin el wrapper
            clean_content = re.sub(r"<[|｜]DSML[|｜][^>]*>.*?</[|｜]DSML[|｜][^>]*>", "", clean_content, flags=re.DOTALL)
            response.content = clean_content.strip()
            
    return {"messages": [response]}


def build_graph(
    tools: List[BaseTool], 
    system_prompt: str, 
    checkpointer: Optional[BaseCheckpointSaver] = None
) -> StateGraph:
    '''Construye el grafo de ejecución con validación y resiliencia.'''
    tool_map = {tool.name: tool for tool in tools}
    guard = SQLGuard(dialect="mysql")
    
    llm = ChatOpenAI(
        model="deepseek-chat", 
        temperature=0, 
        api_key=os.getenv("DEEPSEEK_API_KEY"), 
        base_url="https://api.deepseek.com"
    )
    
    sql_tools = [t for t in tools if t.name == "query"]
    campaign_tool_names = ["list_campaigns", "preview_users_segmentation", "create_campaign", "update_campaign", "delete_campaign"]
    campaign_tools = [t for t in tools if t.name in campaign_tool_names]
    api_tools = [t for t in tools if t.name not in (["query"] + campaign_tool_names)]

    llm_with_tools_map = {
        "DATABASE": llm.bind_tools(sql_tools),
        "CAMPAIGNS": llm.bind_tools(campaign_tools),
        "API": llm.bind_tools(api_tools),
        "GENERAL": llm 
    }

    async def validated_tool_node(state: AgentState):
        '''Ejecuta herramientas en PARALELO con auto-reparación silenciosa.'''
        last_message = state["messages"][-1]
        
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            return {"messages": []}

        from core.application.container import Container
        tool_provider = Container.get_tool_provider()

        async def run_single_tool(tool_call, retry=True):
            name = tool_call["name"]
            args = tool_call["args"]
            tid = tool_call["id"]
            
            logger.info(f"Iniciando ejecución de herramienta: {name}")
            
            # Validación de Seguridad AST
            if name == "query":
                sql = args.get("sql", "")
                is_safe, safe_sql, error_msg = guard.validate_and_transpile(sql)
                if not is_safe:
                    logger.warning(f"Consulta bloqueada: {error_msg}")
                    return ToolMessage(content=f"⛔ BLOQUEO DE SEGURIDAD: {error_msg}", tool_call_id=tid, name=name)
                args["sql"] = safe_sql or sql

            # Obtención dinámica de la herramienta para soportar re-conexión
            available_tools = await tool_provider.get_tools()
            tool = next((t for t in available_tools if t.name == name), None)
            
            if not tool:
                return ToolMessage(content=f"Error: Herramienta '{name}' no disponible.", tool_call_id=tid, name=name)

            try:
                # Ejecución con timeout estándar
                output = await asyncio.wait_for(tool.ainvoke(args), timeout=70.0)
                return ToolMessage(content=str(output), tool_call_id=tid, name=name)
            
            except Exception as e:
                err_info = repr(e)
                
                # DETECCIÓN DE CONEXIÓN ROTA Y REINTENTO SILENCIOSO
                if retry and ("ClosedResourceError" in err_info or "Connection closed" in err_info):
                    logger.warning(f"🔄 Reintento silencioso para '{name}' tras detectar conexión rota.")
                    await tool_provider.report_tool_failure(name)
                    # Recursión simple: un solo reintento para evitar bucles infinitos
                    return await run_single_tool(tool_call, retry=False)

                # Si el reintento también falla o es otro error, reportamos
                logger.error(f"Fallo crítico en '{name}': {err_info}")
                return ToolMessage(
                    content=f"❌ Error técnico en '{name}': {err_info}", 
                    tool_call_id=tid, 
                    name=name
                )

        # Ejecución paralela de todas las herramientas
        results = await asyncio.gather(*(run_single_tool(tc) for tc in last_message.tool_calls))
        return {"messages": list(results)}

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