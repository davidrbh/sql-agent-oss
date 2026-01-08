import os
import ast
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from sqlalchemy import text

# Importaciones de Arquitectura
from sql_agent.llm.factory import LLMFactory
from sql_agent.core.state import AgentState
from sql_agent.config.loader import ConfigLoader
from sql_agent.database.connection import DatabaseManager

# --- IMPORTACIÓN DE LA API (NUEVA UBICACIÓN) ---
try:
    from sql_agent.api.loader import load_api_tools
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

    # --- NODO 1: SQL GENERATOR ---
    async def write_query(self, state: AgentState):
        print("🤖 [Node: SQL] Generando consulta...")
        current_iter = state.get("iterations") or 0
        previous_error = state.get("sql_result", "")
        
        error_context = ""
        if previous_error and "Error" in str(previous_error) and current_iter > 0:
            print(f"   ⚠️ Reintentando corrección SQL ({current_iter})...")
            error_context = f"ERROR PREVIO: {previous_error}. CORRIGE LA CONSULTA."

        prompt = ChatPromptTemplate.from_template(
            """
            Eres un experto SQL. Genera una consulta MySQL compatible.
            
            ESQUEMA:
            {dictionary}
            
            ERRORES PREVIOS:
            {error_context}
            
            PREGUNTA: "{question}"
            
            Responde SOLO el código SQL. Sin markdown.
            """
        )
        chain = prompt | self.llm
        response = await chain.ainvoke({
            "dictionary": self.data_dictionary,
            "error_context": error_context,
            "question": state["question"]
        })
        sql = self._clean_content(response.content).replace("```sql", "").replace("```", "").strip()
        return {"sql_query": sql, "iterations": current_iter + 1}

    # --- NODO 2: SQL EXECUTOR ---
    async def execute_query(self, state: AgentState):
        print("⚡ [Node: Exec] Ejecutando SQL...")
        try:
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

    # --- NODO 3: API EXECUTOR (NUEVO) ---
    async def run_api_tool(self, state: AgentState):
        """
        Ejecuta API con MEMORIA DE CONTEXTO y Protección Anti-Alucinaciones.
        """
        print("🌐 [Node: API] Ejecutando llamada a herramienta...")
        
        if not self.api_tools:
            return {"sql_result": "Error: Las herramientas de API no están configuradas."}

        from langgraph.prebuilt import create_react_agent

        # 1. Reglas (System Message)
        instructions = """
        Eres un operador de APIs preciso.
        REGLAS:
        1. Usa las herramientas para obtener datos REALES.
        2. Si falla, reporta el error exacto.
        3. NO inventes datos.
        4. USA EL CONTEXTO: Si el usuario dice "ese endpoint", refiérete al último mencionado en la charla.
        """
        
        api_agent = create_react_agent(self.llm, self.api_tools)
        
        # 2. PREPARAR MEMORIA (CRÍTICO) 🧠
        # Obtenemos el historial previo del estado global
        # Filtramos para no duplicar la pregunta actual si ya está en la lista
        history = state.get("messages", [])
        
        # Si el historial tiene mensajes, los usamos. Si no, lista vacía.
        # Truco: Tomamos los últimos 5 mensajes para dar contexto sin saturar
        recent_history = history[-5:] if history else []

        # 3. Construir la entrada completa para el sub-agente
        # Orden: [Instrucciones Sistema] -> [Historial Chat] -> [Pregunta Actual]
        input_messages = [SystemMessage(content=instructions)] + recent_history
        
        # Verificamos si el último mensaje del historial es la pregunta actual.
        # Si NO lo es, agregamos la pregunta manualmente.
        if not recent_history or recent_history[-1].content != state["question"]:
            input_messages.append(HumanMessage(content=state["question"]))

        try:
            # Ejecutamos con contexto
            result = await api_agent.ainvoke({"messages": input_messages})
            
            last_message = result["messages"][-1].content
            print(f"   🔙 [DEBUG API]: {str(last_message)[:300]}...") 
            return {"sql_result": f"[Origen API] {last_message}"}
            
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