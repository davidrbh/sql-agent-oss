from typing import Optional, Any

class MCPManager:
    _session: Optional[Any] = None

    def set_session(self, session: Any):
        """Inicializa la sesión MCP globalmente."""
        self._session = session
        print("✅ [MCP Manager] Sesión MCP enlazada correctamente.")

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Invoca una herramienta genérica del Sidecar."""
        if not self._session:
             raise RuntimeError("MCP Session not initialized")
        
        result = await self._session.call_tool(tool_name, arguments=arguments)
        
        # Procesamiento básico de resultados de texto para compatibilidad
        output = ""
        if hasattr(result, 'content') and result.content:
            for item in result.content:
                if hasattr(item, 'text'):
                    output += item.text
                elif isinstance(item, dict) and 'text' in item:
                        output += item['text']
        return output

    async def execute_query(self, query: str) -> str:
        """Ejecuta una query SQL a través del sidecar MCP."""
        if not self._session:
            raise RuntimeError("⚠️ Intento de usar MCP antes de inicializar la sesión (Lifespan Error)")
        
        print(f"📡 [MCP Manager] Enviando query: {query[:50]}...")
        
        # Llamada al tool 'query' definido en el Sidecar
        # Nota: La firma puede variar según la versión del SDK, asumimos call_tool estándar
        try:
            result = await self._session.call_tool("query", arguments={"sql": query})
            
            # Extraer texto de la respuesta
            output = ""
            if hasattr(result, 'content') and result.content:
                for item in result.content:
                    if hasattr(item, 'text'):
                        output += item.text
                    elif isinstance(item, dict) and 'text' in item:
                         output += item['text']
            
            return output
            
        except Exception as e:
            print(f"❌ [MCP Manager] Error ejecutando tool: {e}")
            raise e

    async def list_tools(self) -> list:
        """Lista las herramientas disponibles en el Sidecar MCP."""
        if not self._session:
            print("⚠️ [MCP Manager] Sesión no inicializada al listar tools.")
            return []
        
        try:
            result = await self._session.list_tools()
            if hasattr(result, 'tools'):
                return result.tools
            return []
        except Exception as e:
            print(f"❌ [MCP Manager] Error listando tools: {e}")
            return []

# Singleton exportado
mcp_manager = MCPManager()
