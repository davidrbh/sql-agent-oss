import os
import yaml
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy import text

# Importaciones internas
from sql_agent.core.state import AgentState
from sql_agent.config.loader import ConfigLoader
from sql_agent.database.connection import DatabaseManager

# Rutas
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
DICTIONARY_PATH = os.path.join(BASE_DIR, 'data', 'dictionary.yaml')

class AgentNodes:
    """
    Contiene las funciones (nodos) que ejecutará el grafo.
    """
    
    def __init__(self):
        # Cargamos configuración
        self.settings = ConfigLoader.load_settings()
        
        # Inicializamos el LLM (Gemini 3 Flash Preview)
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-3-flash-preview",
            temperature=0
        )
        
        # Cargamos el Diccionario de Datos en memoria
        try:
            with open(DICTIONARY_PATH, 'r', encoding='utf-8') as f:
                self.data_dictionary = f.read()
        except FileNotFoundError:
            self.data_dictionary = "No data dictionary found."

    async def write_query(self, state: AgentState):
        """
        NODO 1: Generador de SQL
        Toma la pregunta del usuario + Diccionario -> Genera SQL.
        """
        print("🤖 [Node: Write Query] Pensando SQL...")
        
        prompt = ChatPromptTemplate.from_template(
            """
            Eres un experto en SQL y MySQL. Tienes acceso al siguiente esquema de base de datos (Diccionario de Datos):
            
            {dictionary}
            
            PREGUNTA DEL USUARIO: "{question}"
            
            TU OBJETIVO:
            Generar una consulta SQL válida (MySQL) para responder la pregunta.
            
            REGLAS:
            1. Responde SOLO con el código SQL puro. No uses Markdown (```sql), ni explicaciones.
            2. Usa CURDATE() si preguntan por "hoy".
            3. Si la pregunta no se puede responder con el esquema, devuelve "NO_SQL".
            """
        )
        
        chain = prompt | self.llm
        
        response = await chain.ainvoke({
            "dictionary": self.data_dictionary,
            "question": state["question"]
        })
        
        # Limpieza básica por si el modelo pone markdown
        sql = response.content.replace("```sql", "").replace("```", "").strip()
        
        return {"sql_query": sql}

    async def execute_query(self, state: AgentState):
        """
        NODO 2: Ejecutor de SQL
        Toma el SQL -> Ejecuta en DB -> Devuelve filas o error.
        """
        print("⚡ [Node: Execute Query] Ejecutando en MySQL...")
        
        query_str = state["sql_query"]
        
        if query_str == "NO_SQL":
            return {"sql_result": "Error: No pude generar una consulta válida para tu pregunta."}
            
        engine = DatabaseManager.get_engine()
        
        try:
            async with engine.connect() as conn:
                # Usamos text() para seguridad
                result = await conn.execute(text(query_str))
                rows = result.fetchall()
                keys = result.keys()
                
                # Convertimos a lista de dicts
                data = [{key: str(val) for key, val in zip(keys, row)} for row in rows]
                
                # Limitamos resultados para no saturar el contexto (Safety)
                if len(data) > 20:
                    data = data[:20]
                    data.append({"warning": "Resultados truncados a 20 filas."})
                
                result_str = str(data)
                
        except Exception as e:
            result_str = f"Error SQL: {str(e)}"
            
        return {"sql_result": result_str}

    async def generate_answer(self, state: AgentState):
        """
        NODO 3: Respuesta Final
        Toma Pregunta + SQL + Resultados -> Responde en lenguaje natural.
        """
        print("🗣️ [Node: Answer] Generando respuesta final...")
        
        prompt = ChatPromptTemplate.from_template(
            """
            Actúa como un analista de datos amable.
            
            PREGUNTA ORIGINAL: "{question}"
            QUERY SQL EJECUTADO: "{sql_query}"
            RESULTADO DE LA BASE DE DATOS: "{sql_result}"
            
            INSTRUCCIONES:
            1. Responde la pregunta basándote en los datos.
            2. Si hubo un error, explícalo de forma sencilla.
            3. No menciones IDs numéricos a menos que sea necesario.
            4. Sé breve y directo.
            """
        )
        
        chain = prompt | self.llm
        
        response = await chain.ainvoke({
            "question": state["question"],
            "sql_query": state["sql_query"],
            "sql_result": state["sql_result"]
        })
        
        # Devolvemos el mensaje final como un AIMessage para LangGraph
        return {"messages": [response]}
