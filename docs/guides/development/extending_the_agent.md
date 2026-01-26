# Guía para Extender el Agente con Nuevas Funcionalidades

## 1. Introducción: El Poder de la Arquitectura "Hybrid Slice"

La arquitectura de este proyecto está diseñada para ser modular y extensible. El concepto de "Hybrid Slice" o "Feature Slice" nos permite añadir nuevas capacidades al agente de forma aislada, sin tener que modificar su núcleo (`agent_core`).

Una "feature" es una capacidad autocontenida que le da al agente un nuevo conjunto de habilidades. Por ejemplo:
-   `sql_analysis`: La capacidad de analizar y consultar bases de datos.
-   `pdf_reader`: La capacidad de leer y responder preguntas sobre archivos PDF.
-   `billing_api`: La capacidad de interactuar con una API de facturación.

Esta guía te mostrará, a través de un ejemplo práctico, cómo añadir una nueva feature: un **Lector de PDFs**.

## 2. Anatomía de una "Feature"

Una feature es, en esencia, un directorio dentro de `apps/agent-host/src/features/` que contiene un archivo `loader.py`.

El `loader.py` tiene dos responsabilidades principales:

1.  **`get_tools()`:** Una función asíncrona que devuelve una lista de herramientas (`List[BaseTool]`) que esta feature provee. Estas herramientas son las "manos" del agente, las acciones que puede realizar.
2.  **`get_system_prompt()`:** Una función que devuelve un string (`str`). Este es el "manual de instrucciones" que le dice al LLM cómo debe comportarse y cómo usar las herramientas que se le han dado.

---

## 3. Guía Práctica: Creando la Feature "PDF Reader"

**Escenario:** Queremos que el agente pueda responder a la pregunta: *"Resume las primeras 5 páginas del documento en la ruta '/app/data/informe_anual.pdf'"*.

### Paso 1: Instalar Dependencias

Necesitaremos una librería para leer PDFs. Usaremos `pypdf`. Añade esta línea a la sección `[tool.poetry.dependencies]` de tu archivo `apps/agent-host/pyproject.toml`:

```toml
pypdf = "^4.2.0"
```

Luego, desde dentro del directorio `apps/agent-host`, ejecuta `poetry lock` y `poetry install`, o simplemente reconstruye tu contenedor Docker para que instale la nueva dependencia.

### Paso 2: Crear la Estructura de la Feature

Crea el siguiente directorio y archivo:

-   Directorio: `apps/agent-host/src/features/pdf_reader/`
-   Archivo: `apps/agent-host/src/features/pdf_reader/loader.py`

### Paso 3: Implementar las Herramientas (`get_tools`)

Dentro de `loader.py`, vamos a crear una herramienta que lee un PDF y devuelve su texto.

```python
# apps/agent-host/src/features/pdf_reader/loader.py

from typing import List
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field
import pypdf

# --- Implementación de la Lógica de la Herramienta ---

def summarize_pdf(file_path: str, page_limit: int = 5) -> str:
    """
    Lee un archivo PDF desde una ruta específica, extrae el texto de las primeras 'page_limit' páginas y lo devuelve.
    """
    try:
        text_content = []
        with open(file_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            num_pages = len(reader.pages)
            
            # Limitar el número de páginas a leer
            pages_to_read = min(num_pages, page_limit)
            
            for i in range(pages_to_read):
                page = reader.pages[i]
                text_content.append(f"--- Página {i+1} ---")
                text_content.append(page.extract_text())
                
        return "\n".join(text_content)
    except FileNotFoundError:
        return f"Error: No se encontró el archivo en la ruta '{file_path}'."
    except Exception as e:
        return f"Error procesando el PDF: {e}"

# --- Empaquetado de la Herramienta para LangChain ---

class PdfToolArgs(BaseModel):
    file_path: str = Field(description="La ruta absoluta al archivo PDF que se debe leer.")
    page_limit: int = Field(default=5, description="Número máximo de páginas a leer.")

async def get_tools() -> List[BaseTool]:
    """
    Devuelve la lista de herramientas para esta feature.
    """
    pdf_summary_tool = StructuredTool.from_function(
        func=summarize_pdf,
        name="summarize_pdf",
        description="Extrae y resume el texto de las primeras páginas de un documento PDF.",
        args_schema=PdfToolArgs
    )
    return [pdf_summary_tool]

```

### Paso 4: Implementar el Prompt del Sistema (`get_system_prompt`)

Ahora, en el mismo archivo `loader.py`, le decimos al LLM cómo usar esta nueva herramienta.

```python
# ... (código anterior en el mismo archivo)

def get_system_prompt() -> str:
    """
    Genera el prompt del sistema para la feature de lectura de PDFs.
    """
    return """Eres un asistente experto en el análisis de documentos. Tu tarea principal es ayudar a los usuarios a extraer y resumir información de archivos PDF.

    REGLAS:
    1.  Cuando un usuario te pida leer o resumir un documento, utiliza la herramienta `summarize_pdf`.
    2.  Debes pedir siempre la ruta completa (`file_path`) del documento. Asume que los archivos se encuentran en el directorio `/app/data/` si el usuario no especifica otra cosa.
    3.  Al presentar el resumen, sé claro y formatea bien el texto.
    """
```

### Paso 5: Integrar la Nueva Feature en el Agente

El agente, por defecto, está configurado para usar la feature `sql_analysis`. Para que use nuestra nueva feature (o ambas), debemos modificar el punto de entrada, que es `apps/agent-host/src/main.py`.

Aquí tienes la estrategia recomendada para **combinar múltiples features**:

1.  Abre `apps/agent-host/src/main.py`.
2.  Modifica la función `on_chat_start` para que importe y utilice los `loaders` de todas las features que desees.

```python
# apps/agent-host/src/main.py (extracto modificado)

# ... (otros imports)

# --- IMPORTAR LOADERS DE FEATURES ---
from features.sql_analysis.loader import get_sql_tools, get_sql_system_prompt
from features.pdf_reader.loader import get_tools as get_pdf_tools, get_system_prompt as get_pdf_system_prompt

# ...

@cl.on_chat_start
async def on_chat_start():
    # ... (código de conexión MCP)

    try:
        # ... (código de conexión MCP)
        
        # --- 3. Cargar Herramientas y Contexto (Features Combinadas) ---
        
        # Cargar herramientas de todas las features
        sql_tools = await get_sql_tools(mcp_manager)
        pdf_tools = await get_pdf_tools()
        
        # Combinar las listas de herramientas
        all_tools = sql_tools + pdf_tools
        
        # Combinar los prompts del sistema
        sql_prompt = get_sql_system_prompt()
        pdf_prompt = get_pdf_system_prompt()
        
        combined_prompt = f"""Eres un agente multifuncional. Puedes analizar bases de datos y leer documentos. Decide cuál es la mejor herramienta para la tarea.

---
--- CONTEXTO SQL ---
{sql_prompt}

--- CONTEXTO PDF ---
{pdf_prompt}
"""
        
        tool_names = [t.name for t in all_tools]
        msg.content = f"🔧 Herramientas cargadas: {tool_names}. Construyendo Cerebro Multifuncional..."
        await msg.update()

        # 4. Construir Grafo con las herramientas y el prompt combinados
        graph = build_graph(all_tools, combined_prompt)
        
        # ... (resto del código)

```

## 4. Conclusión

¡Y eso es todo! Al reconstruir y ejecutar tu aplicación, el agente ahora tendrá la capacidad de usar tanto las herramientas de SQL como la nueva herramienta para leer PDFs. El `ToolNode` de LangGraph y el LLM se encargarán de decidir qué herramienta usar en función de la pregunta del usuario.

Este patrón de "features" te permite escalar las capacidades de tu agente de manera casi infinita, manteniendo el código limpio, desacoplado y fácil de mantener.
