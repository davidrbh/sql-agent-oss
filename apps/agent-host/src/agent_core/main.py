import os
from infra.mcp.manager import MCPSessionManager
from features.sql_analysis.loader import get_sql_tools, get_sql_system_prompt



async def build_context():
    """
    Construye el contexto unificado del agente.
    Inicializa la conexión MCP, carga herramientas y el prompt del sistema.
    
    Returns:
        dict: Diccionario con keys 'tools' y 'system_prompt' listo para build_graph(**context).
    """
    print("🔌 [Core] Iniciando contexto del agente...")
    
    # 0. Obtener URL del Sidecar (Resolución Runtime)
    # IMPORTANTE: Se lee aquí y no arriba para asegurar que load_dotenv() ya corrió.
    SIDECAR_URL = os.getenv("SIDECAR_URL", "http://mcp-mysql:3000")
    print(f"🔗 [Core] Sidecar URL: {SIDECAR_URL}")
    
    # 1. Inicializar Conexión MCP
    mcp_manager = MCPSessionManager(SIDECAR_URL)
    await mcp_manager.connect()
    print("✅ [Core] Conexión MCP establecida.")

    # 2. Cargar Herramientas y Prompt (Feature SQL)
    tools = await get_sql_tools(mcp_manager)
    system_prompt = get_sql_system_prompt()
    
    print(f"🔧 [Core] Cargadas {len(tools)} herramientas.")

    # Retornamos un dict que coincida con los argumentos de build_graph(tools, system_prompt)
    return {
        "tools": tools,
        "system_prompt": system_prompt
    }
