# Roadmap de Modernización Arquitectónica: Hacia un Agente Híbrido de Baja Latencia

Este documento, basado en investigaciones recientes sobre "Modernización Arquitectónica de Agentes Híbridos SQL-API", establece la hoja de ruta para evolucionar el sistema actual hacia una arquitectura de producción de alto rendimiento.

## 🎯 El Problema: Latencia Estructural

Nuestra arquitectura actual hereda limitaciones de los diseños prototípicos de primera generación:

1.  **Recreación de Agentes:** El grafo de LangGraph se reconstruye en cada petición (`nodes.py`), consumiendo CPU innecesariamente.
2.  **Ingesta de API Bloqueante:** `OpenAPIToolkit.from_llm` en `loader.py` detiene el arranque al usar un LLM para leer `swagger.json`.
3.  **Monolito de Inferencia:** Se usa un modelo grande para tareas triviales.

## 🗺️ Fases de Optimización

### Fase 1: Optimización de Código (Quick Wins) 🚀

Objetivo: Reducir overhead de Python y latencia base sin cambiar infraestructura.

- [ ] **Implementar Patrón Singleton en `AgentNodes`**:
  - Mover la instanciación de `create_react_agent` y la carga de herramientas al método `__init__`.
  - Compilar el grafo una sola vez al inicio del servidor.
- [ ] **Eliminar Ingesta Dinámica LLM de Swagger**:
  - Reemplazar `OpenAPIToolkit.from_llm` por una carga estática de herramientas.
  - Evitar llamadas de red al LLM solo para "leer" la documentación de la API.

### Fase 2: Arquitectura de Grafos Persistentes (Reliability) 🛡️

Objetivo: Implementar tolerancia a fallos y recuperación.

- [ ] **Checkpointing con Redis**:
  - Usar `langgraph-checkpoint-redis` para guardar el estado después de cada nodo.
  - Permite "Time Travel": si la API falla, reintentar solo ese paso sin re-generar el SQL.
- [ ] **Compilación de Grafos**:
  - Asegurar que `.compile()` se llame durante el arranque, no en tiempo de ejecución.

### Fase 3: Estrategia de Enrutamiento (Model Routing) 🚦

Objetivo: Reducir costos y latencia usando el modelo adecuado para la tarea adecuada.

- [ ] **Router de Vía Rápida (Fast-Path)**:
  - Consultas simples ("listar usuarios", saludos) -> Dirigidas a `gpt-4o-mini` o modelo local.
  - Latencia esperada: <500ms.
- [ ] **Router de Vía Lenta (Slow-Path)**:
  - Consultas analíticas complejas -> Dirigidas a `DeepSeek-V3` / `GPT-4o`.
  - Prioriza precisión sobre velocidad.

### Fase 4: Integración Avanzada (Next-Gen) 🔮

Objetivo: Estandarización y Cacheo Inteligente.

- [ ] **Adopción de MCP (Model Context Protocol)**:
  - Reemplazar `swagger.json` con conectores MCP estandarizados.
  - Permite conexión instantánea ("handshake") sin parsing de esquemas.
- [ ] **Caché Semántico (Redis VL)**:
  - Cachear respuestas basadas en la _intención_ del usuario (vectores) y no en el texto exacto.
  - Ejemplo: "Ventas de ayer" y "¿Cuánto vendimos ayer?" golpean el mismo caché.
- [ ] **Inferencia Local (vLLM)**:
  - Desplegar modelos Open Source (Llama-3) en infraestructura propia para eliminar latencia de red de proveedores públicos.

---

_Referencia: Basado en el informe "Modernización Arquitectónica de Agentes Híbridos SQL-API" (Enero 2026)._
