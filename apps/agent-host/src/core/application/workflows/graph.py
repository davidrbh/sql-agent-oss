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
    '''
    Clasifica la intención del usuario para enrutar al subconjunto de herramientas correcto.
    
    Intenciones soportadas:
      - DATABASE : Consultas SQL a bases de datos relacionales.
      - SHEETS   : Lectura y análisis de hojas de cálculo Google Sheets.
      - API      : Integraciones con servicios REST externos.
      - GENERAL  : Saludos, preguntas generales o charla casual.
    '''
    conversation_history = []
    # Tomamos los últimos mensajes relevantes para contexto
    for msg in state["messages"][-5:]:
        role = "User" if isinstance(msg, HumanMessage) else "AI"
        content = str(msg.content)[:200]
        conversation_history.append(f"{role}: {content}")
    
    context_str = "\n".join(conversation_history)

    prompt = ChatPromptTemplate.from_template(
        """Eres un clasificador de intenciones experto. Analiza la conversación y clasifica la ÚLTIMA petición en:
        - DATABASE: Consultas a bases de datos SQL (tablas, registros, métricas de BD).
        - SHEETS: Consultas sobre hojas de cálculo Google Sheets (datos operativos, campañas de ads, ciclos de vida, CSAT).
        - API: Consultas sobre capacidades generales del sistema o endpoints REST externos.
        - GENERAL: Saludos, preguntas generales o charla casual.
        
        Historial:
        {context}
        
        Responde ÚNICAMENTE con una palabra: DATABASE, SHEETS, API o GENERAL.
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
        elif "SHEETS" in intent_raw: intent = "SHEETS"
        elif "API" in intent_raw: intent = "API"
    except Exception as e:
        logger.error("Error en clasificación de intención: %s", e)
        
    logger.info("Intención detectada: %s", intent)
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
            "\n\n[INSTRUCCIÓN DINÁMICA]: Estás en modo DATABASE. Prioriza el uso de 'query' para consultar la base de datos."
        )
    elif state["intent"] == "SHEETS":
        full_system_content += (
            "\n\n[INSTRUCCIÓN DINÁMICA]: Estás en modo SHEETS. Usa las herramientas de Google Sheets "
            "(get_sheet_data, list_spreadsheets, list_sheets, get_multiple_sheet_data) para responder la consulta."
        )
    elif state["intent"] == "API":
        full_system_content += (
            "\n\n[INSTRUCCIÓN DINÁMICA]: Estás en modo API. Usa las herramientas de integración REST disponibles."
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
    
    # Partición de herramientas por dominio para binding selectivo al LLM.
    # Cada intención recibe solo las herramientas relevantes, reduciendo la
    # probabilidad de alucinaciones en la selección de herramienta.
    sql_tool_names = {"query"}
    sheets_tool_names = {
        "get_sheet_data", "list_spreadsheets", "list_sheets",
        "get_multiple_sheet_data", "get_multiple_spreadsheet_summary",
        "find_in_spreadsheet", "search_spreadsheets",
    }

    sql_tools = [t for t in tools if t.name in sql_tool_names]
    sheets_tools = [t for t in tools if t.name in sheets_tool_names]
    # API tools: todo lo que no sea SQL ni Sheets
    api_tools = [t for t in tools if t.name not in (sql_tool_names | sheets_tool_names)]

    llm_with_tools_map = {
        "DATABASE" : llm.bind_tools(sql_tools) if sql_tools else llm,
        "SHEETS"   : llm.bind_tools(sheets_tools) if sheets_tools else llm,
        "API"      : llm.bind_tools(api_tools) if api_tools else llm,
        "GENERAL"  : llm,
    }

    # Límite de caracteres por respuesta de herramienta (~20K tokens para DeepSeek).
    MAX_TOOL_OUTPUT_CHARS = 80_000

    # Herramientas de Google Sheets que usan el parámetro 'sheet'
    SHEETS_TOOLS_WITH_SHEET_PARAM = {
        "get_sheet_data", "get_multiple_sheet_data", "update_cells",
        "add_rows", "batch_update_cells", "get_sheet_formulas"
    }

    def _quote_sheet_name(name: str) -> str:
        '''Envuelve nombres de hoja con espacios en comillas simples para la API de Google Sheets.'''
        if name and ' ' in name and not name.startswith("'"):
            return f"'{name}'"
        return name

    def _sanitize_sheets_args(name: str, args: dict) -> dict:
        '''Corrige argumentos de herramientas de Google Sheets antes de la ejecución.'''
        if name not in SHEETS_TOOLS_WITH_SHEET_PARAM:
            return args
        
        # Quotear el parámetro 'sheet' si tiene espacios
        if 'sheet' in args:
            args['sheet'] = _quote_sheet_name(args['sheet'])
        
        # Quotear nombre de hoja dentro del parámetro 'range' (ej: "Hoja 1!A1:F10")
        if 'range' in args and args['range'] and '!' in args['range']:
            parts = args['range'].split('!', 1)
            parts[0] = _quote_sheet_name(parts[0])
            args['range'] = '!'.join(parts)

        # Para get_multiple_sheet_data, sanitizar cada query del array
        if name == 'get_multiple_sheet_data' and 'queries' in args:
            queries = args['queries']
            if isinstance(queries, list):
                for q in queries:
                    if isinstance(q, dict) and 'sheet' in q:
                        q['sheet'] = _quote_sheet_name(q['sheet'])
                    if isinstance(q, dict) and 'range' in q and q['range'] and '!' in q['range']:
                        parts = q['range'].split('!', 1)
                        parts[0] = _quote_sheet_name(parts[0])
                        q['range'] = '!'.join(parts)
        
        return args

    def _truncate_output(output: str, tool_name: str) -> str:
        '''Trunca respuestas de herramientas que exceden el límite para evitar desbordar el contexto del LLM.'''
        if len(output) <= MAX_TOOL_OUTPUT_CHARS:
            return output
        
        truncated = output[:MAX_TOOL_OUTPUT_CHARS]
        warning = (
            f"\n\n⚠️ RESPUESTA TRUNCADA: La herramienta '{tool_name}' devolvió {len(output):,} caracteres. "
            f"Se muestran los primeros {MAX_TOOL_OUTPUT_CHARS:,}. "
            f"Pide al usuario que sea más específico con el rango o los filtros para obtener menos datos."
        )
        logger.warning(f"Truncando salida de '{tool_name}': {len(output):,} -> {MAX_TOOL_OUTPUT_CHARS:,} chars")
        return truncated + warning

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

            # Sanitización de argumentos para Google Sheets
            args = _sanitize_sheets_args(name, args)

            # Obtención dinámica de la herramienta para soportar re-conexión
            available_tools = await tool_provider.get_tools()
            tool = next((t for t in available_tools if t.name == name), None)
            
            if not tool:
                return ToolMessage(content=f"Error: Herramienta '{name}' no disponible.", tool_call_id=tid, name=name)

            try:
                # Ejecución con timeout estándar
                output = await asyncio.wait_for(tool.ainvoke(args), timeout=70.0)
                # Truncar respuestas demasiado grandes para el LLM
                content = _truncate_output(str(output), name)
                return ToolMessage(content=content, tool_call_id=tid, name=name)
            
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