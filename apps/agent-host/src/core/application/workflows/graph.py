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

# -----------------------------------------------------------------------
# Constantes de módulo (accesibles desde agent_node y build_graph)
# -----------------------------------------------------------------------
SHEETS_PAGE_SIZE = 200  # Filas máximas por página de Google Sheets


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
        """Eres un clasificador de intenciones experto. Este agente está ESPECIALIZADO en Google Sheets como fuente de datos principal.

Clasifica la ÚLTIMA petición del usuario en UNA de estas categorías:

- SHEETS: CUALQUIER consulta sobre datos, métricas, reportes, análisis, contactos, ventas, ciclos de vida, conversaciones, CSAT, ads, campañas, gráficos, distribuciones o estadísticas. Esta es la intención POR DEFECTO cuando el usuario pide información de negocio.
- DATABASE: SOLO cuando el usuario menciona EXPLÍCITAMENTE "SQL", "base de datos", "tabla SQL", "query" o pide ejecutar una consulta a una base de datos relacional.
- API: Consultas sobre capacidades del sistema, endpoints REST, integraciones externas o notificaciones (Lysto, campañas push).
- GENERAL: Saludos, preguntas generales, charla casual, o preguntas que NO involucran datos.

REGLA CLAVE: Si hay duda entre SHEETS y DATABASE, SIEMPRE elige SHEETS.

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
            "(get_sheet_data, list_spreadsheets, list_sheets, get_multiple_sheet_data) para responder la consulta.\n\n"
            "PAGINACIÓN AUTOMÁTICA:\n"
            f"- Los datos se devuelven en páginas de máximo {SHEETS_PAGE_SIZE} filas.\n"
            "- Al final de cada respuesta verás un bloque 📄 PAGINACIÓN con el rango de la siguiente página.\n"
            "- Si necesitas más datos (ej: totales, conteos completos), solicita páginas adicionales usando el rango indicado.\n"
            "- Si la página devolvió menos filas de las esperadas, ya llegaste al final de los datos.\n"
            "- SIEMPRE indica al usuario cuántas filas analizaste y si hay más páginas disponibles."
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

    # -----------------------------------------------------------------------
    # Constantes de paginación y protección de contexto
    # -----------------------------------------------------------------------
    SHEETS_MAX_COL   = "Z"          # Columna máxima por defecto
    MAX_TOOL_OUTPUT_CHARS = 80_000  # Límite duro de caracteres (~20K tokens para DeepSeek)

    # Herramientas de Google Sheets que aceptan el parámetro 'sheet'
    SHEETS_TOOLS_WITH_SHEET_PARAM = {
        "get_sheet_data", "get_multiple_sheet_data", "update_cells",
        "add_rows", "batch_update_cells", "get_sheet_formulas"
    }
    # Subconjunto de herramientas de lectura que deben paginarse
    SHEETS_PAGINATED_TOOLS = {"get_sheet_data"}

    # -----------------------------------------------------------------------
    # Helpers de sheets: quoting, pagination, truncation
    # -----------------------------------------------------------------------

    def _quote_sheet_name(name: str) -> str:
        '''
        Envuelve nombres de hoja con espacios en comillas simples.

        La API de Google Sheets requiere que los nombres con caracteres
        especiales o espacios estén entre comillas simples en la notación A1
        (ej: "'Hoja 1'!A1:F10").
        '''
        if name and ' ' in name and not name.startswith("'"):
            return f"'{name}'"
        return name

    def _parse_row_from_range(range_str: str) -> tuple:
        '''
        Extrae los números de fila de inicio y fin de una cadena en notación A1.

        Args:
            range_str: Rango en notación A1, ej: "A1:Z200" o "'Hoja 1'!A201:Z400".

        Returns:
            tuple: (start_row: int, end_row: int) o (None, None) si no se puede parsear.
        '''
        # Eliminar prefijo de hoja si existe (ej: "'Hoja 1'!A1:Z200" → "A1:Z200")
        clean = range_str.split('!')[-1] if '!' in range_str else range_str
        match = re.match(r'([A-Z]+)(\d+):([A-Z]+)(\d+)', clean)
        if match:
            return int(match.group(2)), int(match.group(4))
        return None, None

    def _apply_default_pagination(name: str, args: dict) -> dict:
        '''
        Inyecta un rango paginado por defecto cuando el LLM no especifica uno.

        Si la herramienta es de lectura y no se proporcionó rango, establece
        automáticamente "A1:Z{PAGE_SIZE}" para acotar la primera página y evitar
        desbordar el contexto del LLM con hojas gigantes.

        Args:
            name: Nombre de la herramienta invocada.
            args: Argumentos originales del tool_call.

        Returns:
            dict: Argumentos con el rango paginado inyectado si corresponde.
        '''
        if name not in SHEETS_PAGINATED_TOOLS:
            return args

        range_val = args.get('range', '') or ''
        if not range_val.strip():
            default_range = f"A1:{SHEETS_MAX_COL}{SHEETS_PAGE_SIZE}"
            args['range'] = default_range
            logger.info(
                f"[Pagination] Rango vacío en '{name}'. Inyectando página por defecto: {default_range}"
            )

        return args

    def _sanitize_sheets_args(name: str, args: dict) -> dict:
        '''
        Pipeline de sanitización para herramientas de Google Sheets.

        Aplica secuencialmente:
          1. Paginación por defecto (inyecta rango si falta).
          2. Quoting de nombres de hoja con espacios.

        Args:
            name: Nombre de la herramienta.
            args: Argumentos originales del tool_call.

        Returns:
            dict: Argumentos corregidos, listos para la API de Google Sheets.
        '''
        if name not in SHEETS_TOOLS_WITH_SHEET_PARAM and name not in SHEETS_PAGINATED_TOOLS:
            return args

        # Paso 1: Inyectar paginación si no hay rango explícito
        args = _apply_default_pagination(name, args)

        # Paso 2: Quotear el parámetro 'sheet' si tiene espacios
        if 'sheet' in args:
            args['sheet'] = _quote_sheet_name(args['sheet'])

        # Paso 3: Quotear nombre de hoja dentro del parámetro 'range' (ej: "Hoja 1!A1:F10")
        if 'range' in args and args['range'] and '!' in args['range']:
            parts = args['range'].split('!', 1)
            parts[0] = _quote_sheet_name(parts[0])
            args['range'] = '!'.join(parts)

        # Paso 4: Para get_multiple_sheet_data, sanitizar cada query del array
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

    def _build_pagination_hint(tool_name: str, args: dict, output: str) -> str:
        '''
        Construye metadata de paginación para anexar a la respuesta de la herramienta.

        Si la herramienta es paginable, analiza el rango utilizado y genera una
        indicación estructurada con la siguiente página disponible, permitiendo
        que el LLM se auto-pagine de forma autónoma.

        Args:
            tool_name: Nombre de la herramienta ejecutada.
            args: Argumentos con los que se ejecutó.
            output: Respuesta original de la herramienta.

        Returns:
            str: Respuesta original con metadata de paginación anexada,
                 o la respuesta sin cambios si no corresponde paginar.
        '''
        if tool_name not in SHEETS_PAGINATED_TOOLS:
            return output

        range_used = args.get('range', '')
        if not range_used:
            return output

        start_row, end_row = _parse_row_from_range(range_used)
        if start_row is None or end_row is None:
            return output

        rows_fetched = end_row - start_row + 1
        next_start = end_row + 1
        next_end = next_start + SHEETS_PAGE_SIZE - 1

        # Determinar el spreadsheet_id y sheet para el hint de siguiente página
        spreadsheet_id = args.get('spreadsheet_id', '<spreadsheet_id>')
        sheet = args.get('sheet', '')
        next_range = f"A{next_start}:{SHEETS_MAX_COL}{next_end}"

        pagination_meta = (
            f"\n\n📄 PAGINACIÓN | Filas {start_row}-{end_row} ({rows_fetched} filas mostradas).\n"
            f"➡️ Para obtener la siguiente página, llama a get_sheet_data con:\n"
            f"   spreadsheet_id='{spreadsheet_id}', sheet='{sheet}', range='{next_range}'\n"
            f"⚠️ Si la respuesta devolvió menos de {SHEETS_PAGE_SIZE} filas, ya no hay más datos."
        )

        return output + pagination_meta

    def _truncate_output(output: str, tool_name: str) -> str:
        '''
        Red de seguridad: trunca respuestas que aún excedan el límite.

        Opera como último recurso después de la paginación. Si por alguna razón
        la respuesta paginada sigue siendo demasiado grande, corta el contenido
        y notifica al LLM para que solicite rangos más acotados.

        Args:
            output: Respuesta de la herramienta (posiblemente ya paginada).
            tool_name: Nombre de la herramienta para el mensaje de warning.

        Returns:
            str: Respuesta truncada con advertencia, o la original si cabe.
        '''
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
                content = str(output)
                # Anexar metadata de paginación para herramientas de Sheets
                content = _build_pagination_hint(name, args, content)
                # Red de seguridad: truncar si aún excede el límite
                content = _truncate_output(content, name)
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