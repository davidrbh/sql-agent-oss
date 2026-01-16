from typing import List, Any, Dict, Type, Optional
from langchain_core.tools import StructuredTool, BaseTool
from mcp import ClientSession
from pydantic import BaseModel, create_model, Field

def _create_args_schema(tool_name: str, schema: Dict[str, Any]) -> Type[BaseModel]:
    """
    Creates a Pydantic model from a JSON Schema.
    Simplistic implementation for flat schemas common in our MCP tools.
    """
    fields = {}
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    
    # Mapping simplified for common JSON types
    type_map = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict
    }

    for prop_name, prop_def in properties.items():
        json_type = prop_def.get("type", "string")
        # Handle simple type mapping
        py_type = type_map.get(json_type, Any)
        
        description = prop_def.get("description", "")
        
        # Determine if required or optional
        if prop_name in required:
            fields[prop_name] = (py_type, Field(..., description=description))
        else:
            fields[prop_name] = (Optional[py_type], Field(None, description=description))
            
    # Create the model dynamically
    # Use a sanitized name for the class
    safe_name = tool_name.replace("-", "_").replace(" ", "_").capitalize() + "Schema"
    return create_model(safe_name, **fields)

async def get_agent_tools(session: ClientSession) -> List[BaseTool]:
    """
    Manual implementation of MCP to LangChain tool conversion 
    to avoid library version mismatches and 'config' arg errors.
    """
    if not session:
        print("⚠️ Warning: session is None in get_agent_tools")
        return []

    try:
        # 1. Fetch tool definitions
        print("🔍 Fetching tools from MCP session...")
        result = await session.list_tools()
        tools: List[BaseTool] = []

        print(f"📦 Found {len(result.tools)} tools from sidecar.")

        for tool_def in result.tools:
            # 2. Create Dynamic Pydantic Model for Arguments
            input_schema = tool_def.inputSchema or {}
            # print(f"  - Processing tool: {tool_def.name}")
            args_model = _create_args_schema(tool_def.name, input_schema)
            
            # 3. Define the async execution function
            # We capture 'name' via default arg to avoid loop variable binding issues
            # We use **kwargs to match the Pydantic model fields flatly
            async def _run_tool(
                _tool_name: str = tool_def.name,
                **kwargs
            ) -> str:
                try:
                    # print(f"▶️ Executing tool: {_tool_name} with args: {kwargs}")
                    # Validate: filter out any None values for optional args if needed, 
                    # but MCP usually handles nulls fine.
                    
                    # Filter arguments that are not in the schema (Langchain might inject others)
                    # Actually, **kwargs captures what matched the schema.
                    
                    call_result = await session.call_tool(_tool_name, arguments=kwargs)
                    
                    # Process result content
                    output_text = []
                    if call_result.content:
                        for content in call_result.content:
                            if content.type == 'text':
                                output_text.append(content.text)
                            elif content.type == 'image':
                                output_text.append("[Image Content Not Supported]")
                            elif content.type == 'resource':
                                output_text.append(f"[Resource: {content.resource.uri}]")
                                
                    final_text = "\n".join(output_text)
                    if call_result.isError:
                        return f"Error from tool {_tool_name}: {final_text}"
                    return final_text
                except Exception as e:
                    return f"Error executing tool {_tool_name}: {str(e)}"

            # 4. Wrap with LangChain's StructuredTool
            langchain_tool = StructuredTool.from_function(
                coroutine=_run_tool,
                name=tool_def.name,
                description=tool_def.description or "",
                args_schema=args_model,
                # Avoid validation errors from extra args
                # infer_schema=False is implied by providing args_schema
            )
            
            tools.append(langchain_tool)
            
        return tools

    except Exception as e:
        print(f"❌ Error loading MCP tools manually: {e}")
        import traceback
        traceback.print_exc()
        return []

