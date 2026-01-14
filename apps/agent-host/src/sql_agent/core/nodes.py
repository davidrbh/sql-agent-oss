import os
import ast
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from sqlalchemy import text
from langgraph.prebuilt import create_react_agent  # MOVED TO TOP-LEVEL

# Importaciones de Arquitectura
from sql_agent.llm.factory import LLMFactory
from sql_agent.core.state import AgentState
from sql_agent.config.loader import ConfigLoader
from sql_agent.database.connection import DatabaseManager

# --- IMPORTACIÓN DE LA API (NUEVA UBICACIÓN) ---
try:
    from sql_agent.api.loader import load_api_tools, load_swagger_summary
    API_AVAILABLE = True
except ImportError as e:
    API_AVAILABLE = False
    print(f"⚠️ [Warning] No se pudo cargar el módulo API: {e}")

# Rutas
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
DICTIONARY_PATH = os.path.join(BASE_DIR, 'data', 'dictionary.yaml')

class AgentNodes:
    
    def __init__(self):
        self.settings = ConfigLoader.load_settings()
        self.llm = LLMFactory.create(temperature=0)
        
        # Carga Diccionario SQL
        try:
            with open(DICTIONARY_PATH, 'r', encoding='utf-8') as f:
                self.data_dictionary = f.read()
        except FileNotFoundError:
            self.data_dictionary = "No data dictionary found."

        # Carga Herramientas API
        self.api_tools = load_api_tools() if API_AVAILABLE else []

        # --- OPTIMIZACIÓN SINGLETON (Fase 1) ---
        # Inicializamos el Agente API una sola vez al arranque para evitar overhead
        if self.api_tools:
            print("🚀 [Init] Compilando Agente API (Singleton)...")
            api_instructions = """
            Eres un operador de APIs preciso.
            REGLAS:
            1. Usa las herramientas para obtener datos REALES.
            2. Si falla, reporta el error exacto.
            3. NO inventes datos.
            4. USA EL CONTEXTO: Si el usuario dice "ese endpoint", refiérete al último mencionado en la charla.
            """
            # Pre-construimos el agente. Al usar state_modifier, inyectamos las instrucciones sistema
            # [FIX] state_modifier no disponible en esta versión, inyectamos SystemMessage manualmente en runtime
            self.api_agent_executor = create_react_agent(self.llm, self.api_tools)
        else:
            self.api_agent_executor = None

    # Guardamos las instrucciones como miembro de clase para usar luego
    API_INSTRUCTIONS = """
            Eres un operador de APIs preciso.
            
            REGLAS OPERATIVAS:
            1. CONSULTAS DE META-DATA (¿Qué endpoints hay? ¿Cuál uso?): 
               - RESPONDE usando SOLO la 'Documentación Dinámica' abajo. 
               - NO uses herramientas (requests_get) para esto.
               
            2. CONSULTAS DE DATOS REALES (Trae usuarios, busca el ID 5):
               - USA la herramienta 'requests_get' para obtener la respuesta de la API.
               - Si falla la conexión, reporta el error.

            Documentación Dinámica (Swagger Summary):
    """ + (load_swagger_summary() if API_AVAILABLE else "")

    def _clean_content(self, content) -> str:
        """Helper para limpiar respuestas."""
        if isinstance(content, list):
            content = "".join([str(item) for item in content])
        content_str = str(content)
        if content_str.strip().startswith("{") and "'text':" in content_str:
            try:
                data = ast.literal_eval(content_str)
                if isinstance(data, dict) and 'text' in data:
                    return str(data['text'])
            except:
                pass 
        return content_str

    # --- NODO 0: ROUTER (CLASIFICADOR) ---
    async def classify_intent(self, state: AgentState):
        print("🚦 [Node: Router] Analizando intención del usuario...")
        
        prompt = ChatPromptTemplate.from_template(
            """
            Eres el Router Inteligente de Credivibes AI.
            Clasifica la siguiente pregunta en una categoría.

            CATEGORÍAS:
            1. DATABASE: Para análisis, reportes históricos, conteos, estadísticas de usuarios/ventas. (Lo que está en SQL).
            2. API: Para consultas de estado en tiempo real, validar un ID específico, o información técnica de endpoints.
            3. GENERAL: Saludos o preguntas fuera de contexto.

            Pregunta: "{question}"

            Responde SOLO una palabra: DATABASE, API, o GENERAL.
            """
        )
        chain = prompt | self.llm
        response = await chain.ainvoke({"question": state["question"]})
        intent = self._clean_content(response.content).strip().upper()
        
        # Limpieza extra por si el LLM dice "Es DATABASE"
        if "DATABASE" in intent: intent = "DATABASE"
        elif "API" in intent: intent = "API"
        else: intent = "GENERAL"
            
        print(f"   👉 Decisión: {intent}")
        return {"intent": intent}

    # --- NODO 1: SQL GENERATOR (AUTO-CORRECCIÓN) ---
    async def write_query(self, state: AgentState):
        current_iter = state.get("iterations") or 0
        previous_error = state.get("sql_result", "")
        
        # Lógica de Retry / Self-Healing
        is_retry = False
        if previous_error and "Error" in str(previous_error) and current_iter > 0:
            print(f"   🩹 [Self-Healing] Detectado error SQL. Intento de corrección #{current_iter}...")
            print(f"      contexto: {str(previous_error)[:100]}...")
            is_retry = True

        prompt_template = """
            Eres un arquitecto de bases de datos MySQL experto.
            Tu tarea es generar UNA sola consulta SQL ejecutable para responder a la pregunta del usuario.

            ESTRUCTURA DE TABLAS (Schema):
            {dictionary}

            REGLAS CRÍTICAS:
            1. Usa SOLO sintaxis MySQL estándar.
            2. NO uses Markdown (```sql ... ```). Devuelve solo el código.
            3. Si la pregunta busca 'últimos' o rankings, usa LIMIT.
            4. Si hay nombres de columnas ambiguos, usa alias de tabla (t1.columna).
        """

        if is_retry:
            prompt_template += f"""
            
            🚨 MODO DE CORRECCIÓN ACTIVADO 🚨
            La consulta anterior FALLÓ con este error:
            "{previous_error}"
            
            ANALIZA EL ERROR Y CORRIGE LA CONSULTA:
            - Si es "no such column": Verifica el diccionario y usa el nombre real.
            - Si es "syntax error": Revisa comas, paréntesis y palabras clave.
            - Si es "ambiguous column": Añade prefijos de tabla.
            """

        # [FIX] Inyectar contexto de mensajes anteriores para resolver referencias ("y los activos?")
        history_text = ""
        messages = state.get("messages", [])
        if messages:
             # Tomamos los últimos 4 mensajes omitiendo el actual (que ya está en question)
             relevant_msgs = messages[:-1][-4:] 
             if relevant_msgs:
                 history_text = "\nCONTEXTO CONVERSACIÓN PREVIA:\n" + "\n".join(
                     [f"- {m.type.upper()}: {m.content}" for m in relevant_msgs]
                 )

        prompt_template += f"""
            {history_text}
            
            PREGUNTA ACTUAL: "{{question}}"
            
            SQL Resultante:
        """

        prompt = ChatPromptTemplate.from_template(prompt_template)
        
        chain = prompt | self.llm
        response = await chain.ainvoke({
            "dictionary": self.data_dictionary,
            "question": state["question"]
        })
        
        sql = self._clean_content(response.content).replace("```sql", "").replace("```", "").strip()
        print(f"   📝 Generado SQL: {sql[:60]}...")
        
        return {"sql_query": sql, "iterations": current_iter + 1}

    # --- NODO 2: SQL EXECUTOR ---
    async def execute_query(self, state: AgentState):
        print("⚡ [Node: Exec] Ejecutando SQL...")
        try:
            from sql_agent.database.connection import DatabaseManager # Importacion local para evitar ciclos si es necesario, pero mejor usar la global
            engine = DatabaseManager.get_engine()
            async with engine.connect() as conn:
                result = await conn.execute(text(state["sql_query"]))
                rows = [dict(row._mapping) for row in result.fetchall()] # Mapeo seguro
                # Truncar si es muy largo
                if len(rows) > 15: rows = rows[:15] + [{"note": "...más resultados..."}]
                return {"sql_result": str(rows)}
        except Exception as e:
            print(f"   ❌ Error SQL: {e}")
            return {"sql_result": f"Error SQL: {e}"}

    # --- NODO 3: API EXECUTOR (OPTIMIZADO) ---
    async def run_api_tool(self, state: AgentState):
        """
        Ejecuta API utilizando el Agente Singleton (Fast-Path).
        """
        print("🌐 [Node: API] Ejecutando llamada a herramienta...")
        
        if not self.api_agent_executor:
            return {"sql_result": "Error: Las herramientas de API no están configuradas."}

        # 2. PREPARAR MEMORIA (CRÍTICO) 🧠
        # Obtenemos el historial previo del estado global
        history = state.get("messages", [])
        
        # Truco: Tomamos los últimos 5 mensajes para dar contexto sin saturar
        recent_history = history[-5:] if history else []

        # 3. Construir la entrada
        # [FIX] Inyectamos SystemMessage manualmente aquí
        input_messages = [SystemMessage(content=self.API_INSTRUCTIONS)] + list(recent_history)
        
        if not recent_history or recent_history[-1].content != state["question"]:
            input_messages.append(HumanMessage(content=state["question"]))

        try:
            # Ejecutamos el grafo pre-compilado
            result = await self.api_agent_executor.ainvoke({"messages": input_messages})
            
            # Recuperamos el último mensaje
            last_message_obj = result["messages"][-1]
            last_message_content = last_message_obj.content
            
            # [OPTIMIZACIÓN] Eliminado chequeo estricto de herramientas (tool_calls_count == 0)
            # Dado que inyectamos el resumen del Swagger en el SystemPrompt, el agente puede
            # responder preguntas sobre "qué endpoints existen" usando su contexto válido sin alucinar.
            # Confiamos en el LLM y el SystemPrompt para no inventar datos.
            
            print(f"   🔙 [DEBUG API]: {str(last_message_content)[:300]}...") 
            return {"sql_result": f"[Origen API] {last_message_content}"}
            
        except Exception as e:
            print(f"   ❌ Error API: {e}")
            return {"sql_result": f"Error ejecutando API: {str(e)}"}

    # --- NODO 4: RESPUESTA FINAL ---
    async def generate_answer(self, state: AgentState):
        print("🗣️ [Node: Answer] Resumiendo...")
        
        prompt = ChatPromptTemplate.from_template(
            """
            Responde al usuario basándote en los datos obtenidos.
            Fuente de datos: {intent}
            Datos: {result}
            Pregunta: {question}
            """
        )
        chain = prompt | self.llm
        res = await chain.ainvoke({
            "intent": state.get("intent", "GENERAL"),
            "result": state.get("sql_result", "Sin datos"),
            "question": state["question"]
        })
        return {"messages": [res]}