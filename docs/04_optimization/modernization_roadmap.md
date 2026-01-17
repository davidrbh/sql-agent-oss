# Roadmap de Evolución y Futuras Capacidades

## 1. Estado Actual (Arquitectura MCP-Nativa)

La arquitectura actual del proyecto ha completado con éxito la migración a un **ecosistema nativo de MCP (Model Context Protocol)**. Este hito es el fundamento de la versión actual y representa un salto cualitativo en la madurez del sistema.

**Logros Clave Completados:**
-   **Desacoplamiento Total:** El agente (`agent-host`) está completamente aislado de la implementación y las credenciales de sus herramientas (como la base de datos).
-   **Arquitectura de Sidecars:** La comunicación se realiza a través de servicios especializados (`mcp-mysql-sidecar`), mejorando la seguridad, el aislamiento de fallos y la escalabilidad.
-   **Optimización de Latencia:** Se han implementado patrones de "Light Mode" para la carga de APIs y una gestión eficiente del ciclo de vida del agente.

Con esta base sólida, el roadmap se enfoca en expandir la inteligencia, la fiabilidad y el rendimiento del sistema.

---

## 2. Fases Futuras

### Fase 1: Fiabilidad y Memoria a Largo Plazo 🧠

El objetivo de esta fase es dotar al agente de una memoria persistente real, permitiendo conversaciones de múltiples turnos que sobrevivan a reinicios y errores.

-   **[ ] Checkpointing con Redis:** Integrar `langgraph-checkpoint-redis` para guardar el estado del grafo de conversación después de cada paso.
    -   **Beneficio:** Si una API o consulta falla, se puede reintentar solo ese paso. Permite conversaciones verdaderamente largas y contextuales, especialmente en canales como WhatsApp.
-   **[ ] Cola de Tareas Persistente:** Migrar las `BackgroundTasks` de FastAPI a un sistema de colas más robusto como Celery o ARQ para garantizar la entrega de respuestas incluso si el `agent-host` se reinicia.

### Fase 2: Inteligencia de Enrutamiento y Eficiencia 🚦

El objetivo es optimizar costos y latencia utilizando el modelo de lenguaje (LLM) adecuado para cada tarea.

-   **[ ] Router de Vía Rápida (Fast-Path):** Implementar un nodo de enrutamiento inicial que identifique tareas simples (saludos, preguntas repetidas, queries sencillas) y las dirija a un LLM más pequeño y rápido (ej. `GPT-4o-mini`, `Llama-3-8B`).
-   **[ ] Router de Vía Lenta (Slow-Path):** Las consultas analíticas complejas que requieran un razonamiento profundo seguirán siendo manejadas por modelos más potentes (`DeepSeek-V3`, `GPT-4o`), priorizando la precisión sobre la velocidad.

### Fase 3: Expansión del Ecosistema de Herramientas (Sidecars) 🛠️

El objetivo es expandir las capacidades del agente añadiendo nuevos "brazos" especializados.

-   **[ ] Sidecar de Sistema de Archivos:** Crear un `mcp-filesystem-sidecar` que exponga herramientas para leer y escribir archivos en un volumen seguro. Esto haría realidad la feature de "PDF Reader" de una forma robusta y aislada.
-   **[ ] Sidecar Genérico de APIs REST:** Desarrollar un sidecar configurable que pueda realizar llamadas a cualquier API REST de terceros. El `agent-host` simplemente le pediría "llama al endpoint X de la API Y", y el sidecar se encargaría de la autenticación y la comunicación.

### Fase 4: Optimización de Inferencia y Rendimiento ⚡

Esta fase se enfoca en llevar el rendimiento al siguiente nivel para casos de uso de alta demanda.

-   **[ ] Caché Semántico con VectorDB:** Implementar un sistema de caché que almacene los resultados de las preguntas no por el texto exacto, sino por su significado semántico (vectores).
    -   **Beneficio:** Las preguntas "¿Cuánto vendimos ayer?" y "dame las ventas del día anterior" golpearían el mismo caché, reduciendo drásticamente las consultas repetidas a la base de datos y el uso de LLMs.
-   **[ ] Inferencia Local (vLLM / Ollama):** Para máxima privacidad y mínima latencia, el roadmap contempla la capacidad de desplegar modelos open-source (como Llama-3 o Mixtral) en infraestructura propia utilizando servidores de inferencia optimizados.