# Especificación Técnica: Migración a Ecosistema MCP (Model Context Protocol)

**Proyecto:** SQL Agent OSS
**Versión Objetivo:** v3.0 (Arquitectura Distribuida)
**Estado:** Propuesta de Investigación / RFC

## 1. Resumen Ejecutivo

El objetivo es desacoplar el monolito actual (`src/sql_agent`) transformando sus dependencias internas ("hardcoded") en una federación de servicios estandarizados. Actualmente, el agente es responsable de *saber cómo* conectarse a la base de datos y *cómo* leer el Swagger. Con MCP, el agente solo sabrá *qué* herramientas tiene disponibles, delegando la ejecución a servidores especializados.

## 2. Análisis de Brecha (Gap Analysis)

| Componente | Implementación Actual (Legacy) | Implementación Futura (MCP) | Ventaja Clave |
| --- | --- | --- | --- |
| **Base de Datos** | `database/inspector.py` + SQLAlchemy (Drivers en código) | **Servidor MCP MySQL** (Stdio/Docker) | Introspección nativa, seguridad granular y aislamiento de drivers. |
| **Integración API** | `api/loader.py` + `requests` + `swagger.json` (Local) | **Servidor MCP OpenAPI** (Dinámico) | Carga automática de endpoints sin mantener lógica de parsing customizada. |
| **Contexto Negocio** | `semantic/hydrator.py` compila a `dictionary.yaml` | **Servidor MCP "Domain Core"** (FastMCP) | El contexto se expone como *Recurso* (`ctx://business/models`), permitiendo actualizaciones en vivo sin re-desplegar. |
| **Orquestación** | `core/nodes.py` ejecuta herramientas Python locales | **Cliente MCP en LangGraph** | Estandarización de interfaz; capacidad de conectar herramientas remotas o locales indistintamente. |

---

## 3. Arquitectura de Servidores Propuesta

Para reemplazar la lógica actual, desplegaremos 3 servidores MCP distintos que el agente consumirá:

### Servidor A: El Guardián de Datos (MySQL MCP)

Reemplaza a `DatabaseManager` y `SchemaExtractor`.

* **Tecnología:** `@modelcontextprotocol/server-mysql` (Node.js) o implementación equivalente en Python.
* **Transporte:** Stdio (Local para baja latencia).
* **Herramientas:** `query` (SELECT only), `list_tables`, `describe_table`.
* **Seguridad:** Usuario de BD con permisos `SELECT` estrictos.

**Configuración:**
```json
"mysql-server": {
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-mysql"],
  "env": { "MYSQL_HOST": "localhost", "MYSQL_USER": "...", "MYSQL_PASS": "..." }
}
```

### Servidor B: La Pasarela API (OpenAPI MCP)

Reemplaza a `src/sql_agent/api/loader.py`.

* **Tecnología:** `mcp-server-openapi` (Python/Node).
* **Estrategia:** En lugar de leer el `swagger.json` y parchear `requests` con tu clase `BaseUrlRequestsWrapper`, este servidor leerá la especificación y expondrá cada endpoint como una herramienta lista para usar.
* **Manejo de Auth:** La autenticación (`API_AUTH_HEADER`) se configura en el arranque del servidor MCP, no en el prompt del agente.

### Servidor C: El Contexto de Negocio (FastMCP Python)

Reemplaza la lógica estática de `hydrator.py`. Este será un servidor personalizado (custom server).

* **Tecnología:** `FastMCP` (Python SDK).
* **Función:** Exponer el contenido de `business_context.yaml` como **Recursos** leíbles.
* **Implementación Conceptual:**
```python
# src/mcp_servers/domain_context.py
from mcp.server.fastmcp import FastMCP
import yaml

mcp = FastMCP("BusinessContext")

@mcp.resource("context://metrics/definitions")
def get_metrics():
    """Devuelve las definiciones de métricas de negocio"""
    with open("config/business_context.yaml") as f:
        data = yaml.safe_load(f)
    return str(data['models'])
```

---

## 4. Guía de Investigación e Implementación

Para ejecutar esta migración, el equipo debe investigar e implementar los siguientes módulos:

### 4.1. Nueva Dependencia: Adaptadores LangChain

Investigar la librería `langchain-mcp-adapters`. Esta es la pieza clave que permite que **LangGraph** hable con MCP.

* **Acción:** Añadir a `pyproject.toml`:
```toml
langchain-mcp-adapters = "^0.0.1"
mcp = "^0.1.0"
```

### 4.2. Refactorización del Cliente (`src/sql_agent/core/client.py`)

Debemos crear un cliente unificado que inicie los 3 servidores al arrancar la aplicación (`app.py`).

**Código de Investigación (Prototipo):**
```python
from langchain_mcp_adapters.client import MultiServerMCPClient

async def init_mcp_client():
    client = MultiServerMCPClient({
        "db": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-mysql"],
            "env": {...} # Credenciales DB
        },
        "api": {
            "command": "uvx",
            "args": ["mcp-server-openapi", "--url", "http://api.local/swagger.json"],
            "env": {...} # Credenciales API
        }
    })
    
    # Inicializar conexión (Handshake)
    await client.initialize()
    
    # Obtener herramientas convertidas automáticamente a formato LangChain
    tools = await client.get_tools()
    return client, tools
```

### 4.3. Modificación del Grafo (`src/sql_agent/graph.py`)

El nodo `execute_query` ya no usará `SQLAlchemy`. Ahora, el agente "decidirá" usar la herramienta `mysql_query` que le proporciona el servidor MCP.

* **Investigación Crítica:** ¿Cómo manejamos el *Self-Healing* (auto-corrección SQL) si la herramienta es externa?
* *Solución:* El servidor MCP devuelve errores estándar (`MCPError`). Debemos capturar esa excepción en el nodo y pasarla al LLM igual que hacíamos con SQLAlchemy.

### 4.4. Integración con WhatsApp (`webhook.py`)

Dado que `webhook.py` utiliza el mismo grafo (`build_graph`), la migración a MCP será transparente para WhatsApp. Sin embargo, se debe investigar el uso de **Sesiones Persistentes** en el cliente MCP para no reiniciar los servidores en cada mensaje de WhatsApp, lo cual añadiría latencia.

* **Recomendación:** Mantener el `MultiServerMCPClient` como una instancia global (Singleton) en `webhook.py`, similar a como se maneja la conexión a DB hoy.

---

## 5. Hoja de Ruta (Roadmap) Sugerida

1. **Semana 1: "Hello World" MCP**
   * Instalar `uv` y el inspector de MCP (`npx @modelcontextprotocol/inspector`).
   * Ejecutar localmente el servidor de MySQL y conectarse con el inspector para ver las tablas de tu base de datos actual.

2. **Semana 2: Servidor de Dominio**
   * Crear el script `src/mcp_servers/domain.py` usando `FastMCP`.
   * Mover la lógica de lectura de YAML allí.
   * Probar que puedes leer `resource://context` desde el inspector.

3. **Semana 3: Integración LangGraph**
   * Modificar `nodes.py` para eliminar `DatabaseManager`.
   * Inyectar las herramientas MCP en el agente ReAct.
   * Probar flujos conversacionales simples ("¿Cuántos usuarios hay?").

4. **Semana 4: Limpieza**
   * Eliminar `src/sql_agent/database/` (ya no se necesita código de conexión).
   * Eliminar `src/sql_agent/api/loader.py` (ya no se necesita parser de Swagger).

## 6. Recursos para el Equipo

* **Documentación Oficial:** [https://modelcontextprotocol.io/](https://modelcontextprotocol.io/)
* **SDK Python:** [https://github.com/modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk)
* **Ejemplos LangChain:** Buscar repositorio `langchain-mcp-adapters` para patrones de integración con grafos.
* **Depuración:** Uso obligatorio de `mcp-inspector` para ver el tráfico JSON-RPC entre el Agente y los Servidores.
