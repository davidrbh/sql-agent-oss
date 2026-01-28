# Arquitectura de Referencia v4.3: Ecosistema SOA de Alto Rendimiento

## 1. Introducción

**SQL Agent OSS** ha evolucionado hacia un **Ecosistema de Micro-Agentes de Grado Industrial (v4.3)**. Esta versión consolida la arquitectura SOA pura pero introduce optimizaciones críticas de latencia, estabilidad de canal y un sistema de configuración cognitiva basado en YAML.

El sistema se basa en cuatro pilares fundamentales:
1.  **Cognición Optimizada:** Razonamiento paralelo y Prompt Caching.
2.  **Ejecución SOA:** Herramientas desacopladas vía MCP.
3.  **Estabilidad de Canal:** Motor NOWEB para WhatsApp.
4.  **Configuración como Código:** Catálogo dinámico de habilidades.

## 2. Diagrama de Arquitectura (v4.3)

```mermaid
graph TD
    User[👤 Usuario] -->|WhatsApp/Telegram/Web| Host[🧠 Agent Host (Python)]
    
    subgraph "Núcleo Cognitivo (v4.3)"
        Host -->|Orquestación| LangGraph[⚡ Grafo de Estado]
        LangGraph -->|Performance| Caching[🚀 Tool Cache & Prompt Caching]
        LangGraph -->|Paralelismo| Parallel[🛤️ Parallel Tool Execution]
        LangGraph -->|Seguridad| Guard[🛡️ SQLGuard AST]
    end

    subgraph "Canales de Salida"
        Host -->|WebSocket| WAHA[📱 WAHA NOWEB Engine]
        Host -->|Polling| TG[✈️ Telegram Bot]
    end

    subgraph "Sidecars MCP"
        Host -->|MCP SSE| MySQLSidecar[📦 MCP MySQL]
        Host -->|MCP SSE| APISidecar[📦 MCP API]
    end
```

## 3. Innovaciones Clave v4.3

### A. Rendimiento Cognitivo (Low Latency)
*   **Prompt Caching:** Estructura de mensajes optimizada para DeepSeek, manteniendo un prefijo estático (Diccionario + Reglas) que reduce el tiempo de procesamiento y el costo.
*   **Parallel Tool Execution:** Ejecución concurrente de múltiples herramientas (ej: consultar la API y la DB al mismo tiempo) reduciendo la latencia total del turno.
*   **Schema Injection:** Inyección dinámica del mapa de tablas en el prompt para eliminar la necesidad de comandos `DESCRIBE` redundantes.

### B. Infraestructura Resiliente
*   **Motor NOWEB:** Migración de Puppeteer (WEBJS) a un motor basado en WebSocket puro. Elimina cuelgues del navegador y reduce el consumo de RAM en un 60%.
*   **Pool Remoto Optimizado:** Configuración de pool de conexiones para MariaDB/MySQL remotos con encolamiento inteligente, permitiendo manejar ráfagas de hasta 50 usuarios concurrentes.

### C. Configuración Dinámica (prompts.yaml)
*   **Separación de Preocupaciones:** La personalidad del agente, las reglas de estilo y las habilidades específicas no están hardcodeadas. 
*   **Multi-Channel UX:** El sistema adapta su tono y formato (conciso para WhatsApp, rico para Web) consultando el catálogo de canales en tiempo real.

## 4. Flujo de Vida de una Petición (Optimizado)

1.  **Recepción:** Webhook recibe el mensaje.
2.  **Inyección:** `loader.py` construye el prompt usando el **Cache de Esquema** y la configuración de canal.
3.  **Razonamiento:** DeepSeek usa el cache de contexto para responder casi instantáneamente.
4.  **Ejecución Paralela:** Si se requieren herramientas, se disparan simultáneamente hacia los Sidecars MCP.
5.  **Respuesta:** El agente sintetiza el resultado respetando las reglas de estilo del canal (vía YAML).