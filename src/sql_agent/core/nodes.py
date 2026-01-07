import os
import ast
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage
from sqlalchemy import text

# Importaciones de Arquitectura
from sql_agent.llm.factory import LLMFactory
from sql_agent.core.state import AgentState
from sql_agent.config.loader import ConfigLoader
from sql_agent.database.connection import DatabaseManager

# Rutas
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
DICTIONARY_PATH = os.path.join(BASE_DIR, 'data', 'dictionary.yaml')

class AgentNodes:
    """
    Nodos del grafo con capacidad de Memoria (Contexto Conversacional),
    Arquitectura Hexagonal y Limpieza Robusta.
    """
    
    def __init__(self):
        self.settings = ConfigLoader.load_settings()
        
        # 1. Fábrica de LLM
        self.llm = LLMFactory.create(temperature=0)
        
        # 2. Carga del Contexto Semántico
        try:
            with open(DICTIONARY_PATH, 'r', encoding='utf-8') as f:
                self.data_dictionary = f.read()
        except FileNotFoundError:
            self.data_dictionary = "No data dictionary found."

    def _clean_content(self, content) -> str:
        """Helper para limpiar respuestas complejas de Gemini."""
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

    async def write_query(self, state: AgentState):
        """
        NODO 1: Generador de SQL con Auto-Corrección Agresiva.
        """
        print("🤖 [Node: Write Query] Pensando SQL...")
        
        # Recuperamos iteración actual (si no existe, es 0)
        current_iter = state.get("iterations") or 0
        
        # --- DETECCIÓN DE ERRORES ---
        previous_error = state.get("sql_result", "")
        previous_query = state.get("sql_query", "")
        error_section = ""
        
        # Si venimos de un fallo, activamos el MODO CORRECCIÓN
        if previous_error and str(previous_error).startswith("Error") and current_iter > 0:
            print(f"   ⚠️ CORRIGIENDO ERROR (Iteración {current_iter})...")
            error_section = f"""
            #######################################################
            🛑 ALERTA DE ERROR CRÍTICO - MODO DE CORRECCIÓN
            #######################################################
            
            TU INTENTO ANTERIOR FALLÓ.
            
            QUERY GENERADO: 
            {previous_query}
            
            ERROR REPORTADO POR LA BASE DE DATOS: 
            {previous_error}
            
            INSTRUCCIONES OBLIGATORIAS PARA CORREGIR:
            1. Lee el error. Si dice "Unknown column", ESA COLUMNA NO EXISTE en esa tabla. ¡Bórrala o busca en otra tabla!
            2. Revisa el <context> (Diccionario) abajo para ver los nombres REALES de las columnas.
            3. NO vuelvas a generar el mismo código SQL. Cámbialo.
            4. Si usaste un alias (ej: u.phone) y falló, quítalo.
            #######################################################
            """
        # ---------------------------

        # Historial de Chat
        recent_messages = state.get("messages", [])[-6:]
        chat_history = []
        for msg in recent_messages:
            if isinstance(msg, HumanMessage):
                chat_history.append(f"Usuario: {msg.content}")
            elif isinstance(msg, AIMessage):
                clean_ai = self._clean_content(msg.content)
                chat_history.append(f"Asistente: {clean_ai}")
        history_str = "\n".join(chat_history) if chat_history else "No hay historial previo."

        prompt = ChatPromptTemplate.from_template(
            """
            <role>
            Eres un Arquitecto de Base de Datos experto en MySQL y DeepSeek SQL.
            Tu misión es generar consultas SQL precisas y corregirlas si fallan.
            </role>

            <context>
            Esquema de la base de datos (VERDAD ABSOLUTA):
            {dictionary}
            </context>

            <conversation_history>
            {chat_history}
            </conversation_history>
            
            {error_section}

            <user_request>
            "{question}"
            </user_request>

            <constraints>
            1. Genera ÚNICAMENTE el código SQL.
            2. NO uses markdown.
            3. Si el usuario pide un dato que NO está en las tablas del esquema (como 'phone' en 'users'), NO LO INVENTES. Usa solo columnas existentes.
            4. Si no es posible responder, di: NO_SQL
            </constraints>
            """
        )
        
        chain = prompt | self.llm
        response = await chain.ainvoke({
            "dictionary": self.data_dictionary,
            "chat_history": history_str,
            "error_section": error_section, # <--- Inyección agresiva
            "question": state["question"]
        })
        
        content_str = self._clean_content(response.content)
        sql = content_str.replace("```sql", "").replace("```", "").strip()
        
        # IMPORTANTE: Retornamos iterations + 1 para que el grafo avance
        return {"sql_query": sql, "iterations": current_iter + 1}

    async def execute_query(self, state: AgentState):
        """NODO 2: Ejecutor en Base de Datos"""
        print("⚡ [Node: Execute Query] Ejecutando en MySQL...")
        
        query_str = state["sql_query"]
        
        if query_str == "NO_SQL" or not query_str or "{" in query_str:
            return {"sql_result": "Error: No se pudo generar una consulta válida."}
            
        engine = DatabaseManager.get_engine()
        
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text(query_str))
                rows = result.fetchall()
                keys = result.keys()
                
                data = [{key: str(val) for key, val in zip(keys, row)} for row in rows]
                
                if len(data) > 20:
                    data = data[:20]
                    data.append({"warning": "Resultados truncados a 20 filas."})
                
                result_str = str(data)
                
        except Exception as e:
            result_str = f"Error de Ejecución SQL: {str(e)}"
            print(f"   ❌ Falló SQL: {query_str}")
            
        return {"sql_result": result_str}

    async def generate_answer(self, state: AgentState):
        """NODO 3: Respuesta en Lenguaje Natural"""
        print("🗣️ [Node: Answer] Generando respuesta final...")
        
        prompt = ChatPromptTemplate.from_template(
            """
            <role>
            Eres un Analista de Datos senior y amable.
            </role>

            <data_context>
            - Pregunta: "{question}"
            - SQL: "{sql_query}"
            - Resultados: "{sql_result}"
            </data_context>

            <instructions>
            1. Responde basándote EXCLUSIVAMENTE en los resultados.
            2. Si no hay datos, dilo claramente.
            3. Sé conciso y profesional.
            </instructions>
            """
        )
        
        chain = prompt | self.llm
        
        response = await chain.ainvoke({
            "question": state["question"],
            "sql_query": state["sql_query"],
            "sql_result": state["sql_result"]
        })
        
        final_content = self._clean_content(response.content)
        response.content = final_content
        
        return {"messages": [response]}