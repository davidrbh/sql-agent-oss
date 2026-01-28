# Roadmap de Evolución y Futuras Capacidades

## 1. Estado Actual (Arquitectura SOA v4.3 - High Performance)

La arquitectura actual del proyecto ha alcanzado un nivel de madurez industrial, completando la **v4.3**. El sistema es ahora un ecosistema SOA de alto rendimiento, optimizado para latencia mínima y estabilidad de canal.

**Logros Clave v4.3:**
-   **📱 WhatsApp Industrial:** Migración exitosa al motor **NOWEB**, eliminando la dependencia de Chromium y mejorando la estabilidad en un 100%.
-   **⚡ Optimización Cognitiva:** Implementación de **Prompt Caching** y **Parallel Tool Execution**, reduciendo el tiempo de respuesta en un 40%.
-   **🛡️ Seguridad AST Progresiva:** Motor **SQLGuard** refinado con análisis recursivo total y soporte para comandos complejos (`WITH`, `EXPLAIN`).
-   **💾 Memoria Persistente:** Integración nativa con PostgreSQL para persistencia de hilos de conversación.
-   **🎨 Catálogo de Prompts:** Personalidad y habilidades configurables 100% vía YAML (`prompts.yaml`).

---

## 2. Fases Futuras

### Fase 1: Inteligencia de Enrutamiento y Eficiencia 🚦

El objetivo es optimizar costos y latencia utilizando el modelo de lenguaje (LLM) adecuado para cada tarea.

-   **[ ] Router de Vía Rápida (Zero-Turn):** Eliminar el nodo de clasificación de intención para tareas obvias, permitiendo que el Agente principal rutee directamente.
-   **[ ] Multi-Model Routing:** Usar un LLM ultra-rápido (como Groq/Llama3) para decisiones de flujo y DeepSeek-V3 para razonamiento analítico pesado.

### Fase 2: Expansión del Ecosistema de Herramientas (Sidecars) 🛠️

El objetivo es expandir las capacidades del agente añadiendo nuevos "brazos" especializados.

-   **[ ] Sidecar de Documentos (PDF/RAG):** Crear un `mcp-document-sidecar` para procesar archivos PDF y realizar búsquedas semánticas sobre ellos.
-   **[ ] Sidecar de Logs y Monitorización:** Permitir al agente consultar el estado de salud de la propia infraestructura y alertar proactivamente por WhatsApp.

### Fase 3: Seguridad y Privacidad Avanzada (Guardrails) 🔒

-   **[ ] Ofuscación PII Automática:** Implementar una capa de filtrado que detecte información personal sensible (emails, teléfonos completos) y los ofusque antes de enviarlos a canales móviles.
-   **[ ] Auditoría de Consultas:** Panel de control para revisar qué consultas SQL han sido bloqueadas por SQLGuard y por qué.

### Fase 4: Optimización de Inferencia y Rendimiento ⚡

-   **[ ] Caché Semántico con VectorDB:** Implementar un sistema de caché que almacene los resultados de las preguntas por su significado semántico (usando ChromaDB).
-   **[ ] RAG de Metadatos:** Carga dinámica de esquemas de tablas basados en la relevancia de la pregunta, permitiendo escalar a cientos de tablas sin saturar el prompt.
