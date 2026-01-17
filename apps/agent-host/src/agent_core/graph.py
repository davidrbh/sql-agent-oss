import os
from typing import List
from langchain_openai import ChatOpenAI
from langchain_core.tools import BaseTool
from langchain_core.messages import ToolMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

# Importa tu estado (asegúrate de que coincida con tu archivo actual)
from agent_core.core.state import AgentState 

# --- La lógica del core es GENÉRICA ---
# No sabe nada de SQL, ni de negocio.
# Solo recibe herramientas y prompts.

def build_graph(tools: List[BaseTool], system_prompt: str) -> StateGraph:
    """Construye y compila el grafo principal del agente.

    Esta función toma una lista de herramientas y un prompt de sistema para
    configurar un grafo de LangGraph con un nodo de agente y un nodo de
    herramientas, permitiendo un flujo de trabajo cíclico para la
    auto-corrección.

    Args:
        tools: Una lista de objetos BaseTool que el agente podrá invocar.
        system_prompt: El string con las instrucciones base para el LLM.

    Returns:
        Un grafo de LangGraph compilado y listo para ser invocado.
    """
    # Configurar el LLM con las herramientas reales
    # Habilitar manejo de errores para que el Agente pueda recuperarse de fallos SQL
    for tool in tools:
        tool.handle_tool_error = True

    # Usamos DeepSeek como LLM principal
    llm = ChatOpenAI(
        model="deepseek-chat",
        temperature=0,
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com"
    )
    llm_with_tools = llm.bind_tools(tools)

    # 2. Nodo del Agente (El Cerebro)
    def agent_node(state: AgentState):
        messages = state["messages"]
        
        # Inyectar System Prompt si no existe
        if not isinstance(messages[0], SystemMessage):
            # Usamos el prompt pasado por argumento
            messages = [SystemMessage(content=system_prompt)] + messages
            
        print(f"DEBUG MESSAGES: {messages}") 

        # --- SANITIZATION FOR DEEPSEEK ---
        # DeepSeek API (OpenAI compat) falla si el contenido de ToolMessage es una lista de dicts.
        # LangChain ToolNode a veces devuelve bloques de contenido multimodal. Lo aplanamos a texto.
        sanitized_messages = []
        for m in messages:
            if isinstance(m, ToolMessage) and isinstance(m.content, list):
                # Unir todos los bloques de texto
                text_content = "".join([
                    block.get("text", "") for block in m.content 
                    if isinstance(block, dict) and block.get("type") == "text"
                ])
                # Crear nueva copia con contenido string
                new_m = ToolMessage(
                    content=text_content, 
                    tool_call_id=m.tool_call_id, 
                    name=m.name,
                    artifact=m.artifact
                )
                sanitized_messages.append(new_m)
            else:
                sanitized_messages.append(m)

        response = llm_with_tools.invoke(sanitized_messages)
        return {"messages": [response]}

    # 3. Nodo de Herramientas (El Brazo)
    # ToolNode de LangGraph ejecuta automáticamente la herramienta que el LLM pida
    # handle_tool_errors=True permite que el nodo capture excepciones y devuelva un mensaje de error al LLM
    tool_node = ToolNode(tools, handle_tool_errors=True)

    # 4. Definición del Flujo (Workflow)
    workflow = StateGraph(AgentState)

    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)

    workflow.set_entry_point("agent")

    # Lógica condicional: ¿El LLM quiere usar una herramienta o responder al usuario?
    def should_continue(state):
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "tools"
        return END

    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            END: END
        }
    )

    # El agente vuelve a pensar después de usar una herramienta
    workflow.add_edge("tools", "agent")

    return workflow.compile()
