# Especificación de Infraestructura y Conectividad (v4.0)

## 1. Orquestación con Docker Compose

El proyecto está diseñado para ser ejecutado como un ecosistema de microservicios orquestado por **Docker Compose**. Esto garantiza un entorno de desarrollo y despliegue consistente, reproducible y aislado.

El archivo `docker-compose.yml` en la raíz del proyecto es la única fuente de verdad para definir, configurar y lanzar todos los componentes del ecosistema v4.0.

## 2. Descripción de Servicios del Ecosistema

El `docker-compose.yml` actualizado orquesta los siguientes servicios:

### 2.1. `agent-host` (El Cerebro)

-   **Rol:** Orquestador principal de Inteligencia Artificial.
-   **Tecnología:** Python 3.11, FastAPI, LangGraph.
-   **Responsabilidad:** Ejecuta el grafo de decisión cognitivo.
-   **Seguridad:** **No posee credenciales de base de datos de negocio.** Solo conoce:
    -   La URL de los sidecars MCP (`http://mcp-mysql:3002/sse`).
    -   La URL de su propia memoria (`postgresql://...`).

### 2.2. `mcp-mysql-sidecar` (El Brazo Ejecutor)

-   **Rol:** Microservicio especializado que actúa como proxy seguro hacia la base de datos de negocio (MySQL).
-   **Tecnología:** Node.js 20, Fastify, MCP SDK.
-   **Responsabilidad:** Ejecutar consultas SQL estrictamente validadas (READ-ONLY).
-   **Seguridad:** Es el **único** contenedor con las credenciales `DB_PASSWORD` de la base de datos de producción.

### 2.3. `agent-memory` (El Hipocampo)

-   **Rol:** Base de datos dedicada para la persistencia del estado del agente.
-   **Tecnología:** PostgreSQL 16 (Alpine).
-   **Responsabilidad:** Almacenar los checkpoints de LangGraph (JSONB) para permitir "Time Travel" y recuperación ante fallos.
-   **Aislamiento:** Está totalmente separada de la base de datos de negocio para evitar contaminación de datos.

### 2.4. `waha` (La Boca)

-   **Rol:** Gateway de WhatsApp API (vía WAHA).
-   **Responsabilidad:** Interfaz de mensajería para usuarios finales.

## 3. Redes y Comunicación Interna

Todos los servicios se comunican a través de una red bridge interna llamada `sql-agent-network`.

### Flujo de Comunicación Seguro:

1.  **Host -> Sidecar:** HTTP/SSE sobre el puerto `3002`. El Host envía comandos MCP ("Ejecuta esta query").
2.  **Host -> Memory:** TCP/Postgres sobre el puerto `5432`. El Host guarda su estado.
3.  **Sidecar -> MySQL (Externo):** TCP/MySQL sobre el puerto `3306`. El Sidecar ejecuta la query real.

## 4. Gestión de Configuración (12-Factor App)

La configuración se inyecta exclusivamente mediante variables de entorno definidas en `.env`.

### Variables Críticas Nuevas (v4.0):

-   `DB_URI`: Cadena de conexión para la `agent-memory`.
-   `MCP_SERVERS_CONFIG`: JSON que define la topología de los sidecars (ej. `{"default": {"transport": "sse", "url": "..."}}`).

> **Nota:** El archivo `.env` nunca se sube al repositorio. Usa `.env.example` como plantilla.
