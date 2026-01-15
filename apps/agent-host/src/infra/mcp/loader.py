from typing import List
from langchain_core.tools import BaseTool
from mcp import ClientSession

# Adaptador oficial que convierte la definición JSON-RPC a objetos Tool de LangChain
from langchain_mcp_adapters.tools import load_mcp_tools

async def get_agent_tools(session: ClientSession) -> List[BaseTool]:
    """
    Consulta al Sidecar qué herramientas tiene disponibles y las convierte
    en herramientas ejecutables para el LLM.
    """
    if not session:
        return []

    # 1. Llamada remota 'tools/list' al Sidecar Node.js
    # 2. Conversión automática de JSON Schema -> Pydantic
    try:
        mcp_tools = await load_mcp_tools(session)
        return mcp_tools
    except Exception as e:
        print(f"❌ Error loading MCP tools: {e}")
        return []

