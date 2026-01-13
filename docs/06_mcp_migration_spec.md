# Especificación Técnica: Migración Enterprise a Ecosistema MCP (V2)

**Proyecto:** SQL Agent OSS  
**Versión Objetivo:** v3.0 (Arquitectura Distribuida / Cloud Native)  
**Estado:** Definición Técnica (V2.1 - Validada para Producción)

## 1. Resumen Ejecutivo (Revisión V2.1)

Esta especificación consolida la arquitectura "Enterprise" para la migración a MCP. Ha sido validada como **GO / APROBADO** para implementación.
El foco central es la robustez en producción: eliminación de "bloatware" en el contenedor principal, aislamiento de fallos mediante **Sidecars**, y seguridad mejorada (Principio de Mínimo Privilegio).

## 2. Decisiones de Arquitectura Críticas

| Área                          | V1 (Naive)                   | V2 (Enterprise)                       | Rationale                                                                                   |
| ----------------------------- | ---------------------------- | ------------------------------------- | ------------------------------------------------------------------------------------------- |
| **Transporte**                | Stdio (Pipes)                | **SSE (Server-Sent Events)**          | Stdio no escala en K8s/Docker. SSE permite separar contenedores y reinicios independientes. |
| **Topología**                 | Monolito (Subprocesos hijos) | **Malla de Servicios (Sidecars)**     | Si MySQL crashea, solo reinicia el sidecar, no el agente.                                   |
| **Gestión de Ciclo de Vida**  | Singleton Global             | **FastAPI Lifespan + AsyncExitStack** | Garantiza conexiones "calientes" y limpieza de recursos.                                    |
| **Interoperabilidad Node/Py** | `npx` invocado desde Python  | **Contenedores Independientes**       | Evita tener que instalar Node.js dentro de la imagen Docker de Python (bloatware).          |
| **Seguridad**                 | Credenciales en Agente       | **Credenciales en Sidecar**           | El Agente (Python) desconoce el password de la BD. Solo pide ejecutar herramientas.         |

---

## 3. Arquitectura de Despliegue (Docker Compose / K8s)

El sistema se dividirá en contenedores especializados (Sidecars). La gran mejora en V2.1 es el movimiento de secretos (DB Credentials) del Agente al Sidecar.

### 3.1. Contenedor Principal: `sql-agent-core`

- **Rol:** Orquestador (LangGraph + FastAPI).
- **Responsabilidad:** Cliente MCP. Se conecta a los sidecars.
- **Configuración:**
  - **SIN Credenciales de BD:** No contiene `MYSQL_PASSWORD` ni `MYSQL_USER`.
  - **Variables:** Solo URLs de conexión.
    - `MCP_MYSQL_URL=http://mcp-mysql:3000/sse`
    - `MCP_FILESYSTEM_URL=http://mcp-fs:3000/sse`

### 3.2. Sidecar A: `mcp-mysql-sidecar`

- **Imagen Base:** Node.js (Alpine).
- **Wrapper:** `supergateway` (Opción A) o custom bridge (Opción B) envolviendo `@modelcontextprotocol/server-mysql`.
- **Configuración:** **POSEE** las credenciales de base de datos.
  - `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`.
- **Función:** Expone el servidor oficial vía SSE en el puerto 3000.

### 3.3. Sidecar B: `mcp-filesystem-sidecar`

- **Rol:** Acceso seguro a logs/contexto.
- **Seguridad:** Sandbox estricto en el volumen `/data/context`.

---

## 4. Estrategia de Implementación (Código)

### 4.1. Gestión de Recursos (`src/api/lifespan.py`)

La gestión de conexiones MCP debe ser resiliente, incluyendo lógica de **Lazy Reconnect** o **Heartbeat** para manejar reinicios de sidecars sin tumbar el agente.

```python
# src/api/lifespan.py PROTOTIPO
from contextlib import asynccontextmanager, AsyncExitStack
from mcp import ClientSession
from mcp.client.sse import sse_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Stack de salida para cerrar conexiones al apagar
    async with AsyncExitStack() as stack:
        # Nota: La implementación real debe manejar reconexión ante fallos (Lazy Reconnect)
        try:
            # Conectar a MySQL Sidecar
            mcp_mysql = await stack.enter_async_context(
                sse_client(url="http://mcp-mysql:3000/sse")
            )
            app.state.mcp_mysql = mcp_mysql
        except Exception as e:
            print(f"Advertencia: No se pudo conectar a Sidecar MySQL al inicio: {e}")
            # Lógica de retry o inicialización lazy aquí

        yield

        # Al salir, el stack cierra todas las conexiones automáticamente
```

### 4.2. Adaptador Proxy para Node.js (Estrategia)

Para la mayoría de servidores MCP oficiales (stdio), necesitamos un **"Stdio-to-SSE Bridge"**.

**Opción A (Recomendada): Usar `supergateway`**
Es una herramienta estándar que expone stdio sobre SSE.

```dockerfile
# Dockerfile.sidecar (Opción A)
FROM node:20-alpine
RUN npm install -g supergateway @modelcontextprotocol/server-mysql
CMD ["supergateway", "--port", "3000", "--stdio", "mcp-server-mysql"]
```

**Opción B (Robusta): Custom Bridge**
Si se requiere más control, se puede usar un script `bridge.js` con Express y el SDK de MCP.

```dockerfile
# Dockerfile.sidecar (Opción B - Custom)
FROM node:20-alpine
RUN npm install -g @modelcontextprotocol/server-mysql
WORKDIR /app
COPY bridge.js .
RUN npm install express cors @modelcontextprotocol/sdk
CMD ["node", "bridge.js", "npx", "@modelcontextprotocol/server-mysql"]
```

---

## 5. Plan de Migración Revisado

1. **Fase 1: Infraestructura (Sidecars)**

   - Crear `Dockerfile.sidecar` genérico para Node.js.
   - Actualizar `docker-compose.yml` para incluir los servicios satélite.
   - Validar comunicación `curl` (SSE Handshake) entre contenedores.

2. **Fase 2: Cliente Resiliente**

   - Implementar `src/api/lifespan.py`.
   - Modificar `app.py` para usar el lifespan.
   - Eliminar lógica de conexión directa a BD en `src/sql_agent/database`.

3. **Fase 3: Integración LangGraph**
   - Actualizar el grafo para usar herramientas dinámicas extraídas de `app.state.mcp_client.tools`.
   - Implementar manejo de errores semántico (si MCP falla, el LLM recibe el error y reintenta).

## 6. Stack Tecnológico Definido

- **Python SDK:** `mcp[sse]` (Soporte nativo cliente SSE).
- **Node Bridge:** Desarrollo custom o uso de `supergateway` (herramienta existente que expone stdio via HTTP).
- **Orquestador:** Docker Compose (Dev) / Helm (Prod).
