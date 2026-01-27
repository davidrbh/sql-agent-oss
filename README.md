# SQL Agent OSS (v4.0)

**Ecosistema de IA Agéntica SOA con Seguridad AST y Persistencia Transaccional**

_Una plataforma de grado empresarial para interactuar con bases de datos y servicios mediante lenguaje natural, diseñada bajo los principios de Arquitectura Orientada a Servicios (SOA) y Model Context Protocol (MCP)._

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Persistent-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![MCP](https://img.shields.io/badge/MCP-Protocol_v1.0-green.svg)](https://modelcontextprotocol.io/)
[![Docker](https://img.shields.io/badge/Docker-Microservices-2496ED)](https://www.docker.com/)
[![Licencia: MIT](https://img.shields.io/badge/Licencia-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🚀 Novedades v4.0 (The Enterprise Update)

Esta versión introduce cambios radicales en la arquitectura para garantizar seguridad y escalabilidad:

-   **🛡️ SQLGuard (Cognitive Firewall):** Validación de consultas mediante análisis de Árbol de Sintaxis Abstracta (AST) y transpilación defensiva. Imposible inyectar DML (`DELETE`, `DROP`) incluso si el LLM alucina.
-   **🔌 Arquitectura SOA/MCP:** El agente ya no tiene drivers de base de datos. Se conecta a "Sidecars" (microservicios) mediante el protocolo estándar MCP.
-   **🧠 Memoria Persistente (ACID):** Nueva base de datos dedicada (`agent-memory`) con PostgreSQL. El agente recuerda el contexto entre reinicios y fallos.
-   **🏗️ Hybrid Slice Architecture:** Código reestructurado para separar limpiamente el Núcleo (Core), la Infraestructura (Infra) y las Capacidades (Features).

## 🏗️ Arquitectura del Ecosistema

El sistema se compone de servicios Docker orquestados:

| Servicio | Rol | Tecnología | Descripción |
| :--- | :--- | :--- | :--- |
| `agent-host` | **Cerebro** | Python / FastAPI | Orquestador LangGraph. No tiene acceso directo a datos. |
| `mcp-mysql` | **Brazo** | Node.js / MCP | Sidecar que ejecuta las consultas SQL de forma aislada. |
| `agent-memory`| **Memoria** | PostgreSQL 16 | Guarda el estado de las conversaciones y checkpoints. |
| `waha` | **Boca** | WhatsApp API | Gateway para mensajería (Opcional). |

## 🚀 Guía de Inicio Rápido

### 1. Prerrequisitos
- Docker Desktop y Git.
- Una base de datos MySQL (con tus datos de negocio) accesible desde tu red.

### 2. Configuración
1.  Clona el repositorio:
    ```bash
    git clone https://github.com/tu_usuario/sql-agent-oss.git
    cd sql-agent-oss
    ```
2.  Crea tu archivo `.env`:
    ```bash
    cp .env.example .env
    ```
3.  Edita `.env` con tus credenciales. **Nota:** Ahora hay una sección nueva para `MEMORY_DB` (puedes dejar los defaults de postgres para desarrollo).

### 3. Despliegue
Levanta el stack completo:
```bash
docker-compose up --build -d
```

Esto iniciará el `agent-host` en el puerto `8000`, el sidecar MCP en el `3002` y la base de datos de memoria.

### 4. Uso
- **Web UI:** Accede a `http://localhost:8000`.
- **API Docs:** `http://localhost:8000/docs`.

---

## 📚 Documentación

Toda la documentación técnica se encuentra centralizada en la carpeta [`docs/`](./docs):

-   [**Arquitectura v4.0**](./docs/01_architecture/overview.md): Visión profunda del diseño SOA y Hybrid Slice.
-   [**Guía de Configuración**](./docs/setup_guides/): Manuales para integraciones específicas.

## 🤝 Contribución
Sigue los estándares de `Clean Architecture` definidos en `docs/01_architecture/overview.md`. Las PRs deben pasar la validación de tipos y tests.

## 📄 Licencia
MIT.