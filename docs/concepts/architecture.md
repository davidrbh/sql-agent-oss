# Arquitectura de Referencia v4.0: Ecosistema SOA Seguro

## 1. Introducción

**SQL Agent OSS** ha madurado hacia un **Ecosistema de Micro-Agentes Seguro y Distribuido (v4.0)**. Esta arquitectura abandona el modelo monolítico para adoptar un enfoque de **Arquitectura Orientada a Servicios (SOA)** basada en el **Model Context Protocol (MCP)**, priorizando la seguridad (Security-First) y la persistencia robusta.

El sistema desacopla estrictamente tres responsabilidades:
1.  **Cognición (Cerebro):** Orquestación y razonamiento.
2.  **Ejecución (Cuerpo):** Herramientas aisladas en Sidecars.
3.  **Memoria (Hipocampo):** Persistencia ACID transaccional.

## 2. Diagrama de Arquitectura (Alto Nivel)

```mermaid
graph TD
    User[👤 Usuario] -->|HTTPS| Host[🧠 Agent Host (Python)]
    
    subgraph "Núcleo Cognitivo (Host)"
        Host -->|Orquestación| LangGraph[⚡ Grafo de Estado]
        LangGraph -->|Validación| Guard[🛡️ SQLGuard (AST)]
        LangGraph -->|Memoria| Checkpointer[💾 Postgres Checkpointer]
    end

    subgraph "Capa de Ejecución (Sidecars MCP)"
        Host -->|MCP Protocol (SSE/Stdio)| Client[🔌 Multi-Server MCP Client]
        Client -->|Conexión| MySQLSidecar[📦 MCP MySQL (Node.js)]
        Client -->|Futuro| APISidecar[📦 MCP OpenAPI (Python)]
    end

    subgraph "Infraestructura de Datos"
        MySQLSidecar -->|Query (Read-Only)| DB[(🗄️ Base de Datos Negocio)]
        Checkpointer -->|State (JSONB)| Memory[(🧠 Base de Datos Memoria)]
    end
```

## 3. Componentes Principales

### A. Agent Host (El Cerebro)
*   **Tecnología:** Python 3.11+, FastAPI, LangGraph.
*   **Responsabilidad:** No ejecuta SQL ni llamadas HTTP directas. Su única función es *pensar*, planificar y delegar tareas a los sidecars.
*   **Gestión de Dependencias:** Utiliza un contenedor de inyección de dependencias (`core/application/container.py`) para gestionar singletons como el pool de conexiones.

### B. Protocolo MCP & Multi-Server Client
*   **Estándar:** Implementa la especificación MCP v1.0.
*   **Flexibilidad:** El `MultiServerMCPClient` permite conectar `N` servidores simultáneamente.
*   **Configuración:** Se define vía JSON en la variable `MCP_SERVERS_CONFIG`, soportando transportes `stdio` (local/rápido) y `sse` (distribuido/Kubernetes).

### C. Persistencia Transaccional (Memoria)
*   **Motor:** PostgreSQL (vía `agent-memory` container).
*   **Tecnología:** `AsyncPostgresSaver` con `psycopg-pool`.
*   **Ventaja:** Permite "Time Travel" (viajar al pasado en la conversación), recuperación ante fallos y análisis de la memoria del agente mediante consultas SQL sobre columnas `JSONB`.

### D. Seguridad Cognitiva (SQLGuard)
Una capa de defensa en profundidad que opera ANTES de que la consulta salga del agente:
1.  **Análisis AST:** Usa `sqlglot` para descomponer la consulta en un árbol sintáctico abstracto.
2.  **Validación Semántica:** Bloquea nodos peligrosos (`DROP`, `DELETE`, `ALTER`) a nivel estructural, no por texto.
3.  **Transpilación Defensiva:** Reescribe la consulta desde cero para eliminar comentarios maliciosos u ofuscación.

## 4. Estructura del Código (Hybrid Slice)

El código sigue un patrón híbrido que mezcla lo mejor de Clean Architecture y Vertical Slices:

```text
src/
├── core/                  # (Clean Arch) Lógica pura y estable
│   ├── domain/            # Entidades (AgentState)
│   ├── ports/             # Interfaces (IToolProvider)
│   └── application/       # Casos de uso (Workflows/Graph)
├── infra/                 # (Adapters) Implementaciones técnicas
│   ├── mcp/               # Cliente MCP y Adaptadores
│   └── memory/            # Persistencia Postgres
└── features/              # (Vertical Slices) Capacidades de Negocio
    └── sql_analysis/      # Feature autocontenida
        ├── tools/         # Reglas específicas (SQLGuard)
        └── loader.py      # Prompts y configuración
```

## 5. Flujo de Vida de una Petición

1.  **Recepción:** El usuario envía "¿Cuántos usuarios hay?" vía Chainlit/WhatsApp.
2.  **Orquestación:** LangGraph recibe el mensaje y consulta su memoria en Postgres.
3.  **Razonamiento:** El LLM decide usar la herramienta `query`.
4.  **Validación:** El nodo `SQLGuard` intercepta la llamada, valida el AST y transpila el SQL.
5.  **Delegación:** El `MultiServerMCPClient` envía la solicitud al Sidecar MySQL.
6.  **Ejecución:** El Sidecar ejecuta la consulta en la BD de negocio y devuelve el JSON.
7.  **Respuesta:** El Agente sintetiza la respuesta y guarda el nuevo estado en Postgres.