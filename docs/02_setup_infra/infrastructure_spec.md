# Especificación de Infraestructura y Conectividad

## 1. Orquestación con Docker Compose

El proyecto está diseñado para ser ejecutado como un sistema de microservicios orquestado por **Docker Compose**. Esto garantiza un entorno de desarrollo y despliegue consistente, reproducible y aislado.

El archivo `docker-compose.yml` en la raíz del proyecto es la única fuente de verdad para definir, configurar y lanzar todos los componentes del ecosistema.

## 2. Descripción de Servicios

El `docker-compose.yml` define los siguientes servicios principales:

### 2.1. `agent-host` (El Cerebro)

-   **Rol:** Es el servicio principal que contiene la lógica del agente de IA. Actúa como un orquestador que consume herramientas, pero no las implementa directamente.
-   **Tecnología:** Python, FastAPI (para exponer APIs), Chainlit (para la interfaz web) y LangGraph (para el grafo de razonamiento).
-   **Seguridad:** Este contenedor es **agnóstico a las credenciales**. No tiene acceso a contraseñas de bases de datos ni a tokens de servicios externos. Su única configuración son las URLs de los sidecars a los que debe conectarse.

### 2.2. `mcp-mysql-sidecar` (El Brazo SQL)

-   **Rol:** Es un microservicio especializado que actúa como un "puente" seguro hacia la base de datos MySQL. Expone la herramienta `query` a través del protocolo MCP.
-   **Tecnología:** Node.js, Fastify y el SDK de MCP.
-   **Seguridad:** Este contenedor es el **único** que posee las credenciales de la base de datos (leídas desde el archivo `.env`). Esto aísla los secretos de la base de datos del resto del sistema.

### 2.3. `waha` (La Boca)

-   **Rol:** Es un gateway de terceros que se conecta a la API de WhatsApp.
-   **Función:** Recibe los mensajes de los usuarios y los reenvía al `agent-host` a través de un webhook. También se utiliza para enviar las respuestas del agente de vuelta al usuario.

## 3. Configuración Centralizada con `.env`

Toda la configuración del sistema (credenciales, URLs, claves de API) se gestiona de forma centralizada en un único archivo `.env` ubicado en la raíz del proyecto.

-   El archivo `.env.example` sirve como plantilla.
-   `docker-compose.yml` es el responsable de leer este archivo y pasar las variables de entorno apropiadas a cada contenedor en el momento del arranque. Por ejemplo, pasa `DB_PASSWORD` solo al sidecar, pero no al `agent-host`.

## 4. Conectividad de Red en Docker

Dentro del entorno de Docker Compose, los servicios pueden comunicarse entre sí utilizando sus nombres de servicio como si fueran nombres de host (hostnames).

-   Docker gestiona una red virtual interna para los contenedores.
-   **Ejemplo:** El `agent-host` se conecta al sidecar de MySQL utilizando la URL `http://mcp-mysql:3000`, donde `mcp-mysql` es el nombre del servicio definido en `docker-compose.yml`.

Esta configuración de red simplifica enormemente la comunicación entre los microservicios del sistema.