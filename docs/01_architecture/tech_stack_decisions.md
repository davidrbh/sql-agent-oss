# Registro de Decisiones de Arquitectura (ADR)

## 1. Adopción de I/O Asíncrono (AsyncIO)

- **Decisión:** Utilizar `asyncpg` y `SQLAlchemy[asyncio]` en lugar de drivers bloqueantes estándar.
- **Justificación:** Los agentes LLM pasan mucho tiempo esperando respuestas de red (latencia de API de OpenAI + latencia de Base de Datos). Un modelo síncrono bloquearía el servidor completo durante estas esperas. El modelo asíncrono permite manejar cientos de usuarios concurrentes en un solo hilo.
- **Consecuencia:** Todo el código debe usar `await`. No se pueden usar librerías bloqueantes en el bucle principal.

## 2. Orquestación con Grafos (LangGraph)

- **Decisión:** Usar una arquitectura de Grafo de Estado en lugar de cadenas lineales (LangChain Chains).
- **Justificación:** Los sistemas Text-to-SQL requieren bucles de retroalimentación (loops). Si el SQL falla, el agente debe volver atrás y corregir. Las cadenas lineales no manejan bien los ciclos ni la persistencia del estado intermedio.
- **Alternativa rechazada:** Cadenas secuenciales simples (frágiles ante errores).

## 3. Seguridad vía Análisis AST (SQLGlot)

- **Decisión:** Validar la seguridad analizando el Árbol de Sintaxis Abstracta (AST) y no mediante expresiones regulares (Regex).
- **Justificación:** Las Regex son fáciles de burlar en SQL (ej: ofuscar un `DROP` con comentarios). SQLGlot entiende la estructura lógica del código, permitiendo bloquear nodos específicos de modificación de datos con certeza matemática.

## 4. Estrategia de "Solo Lectura" (Read-Only)

- **Decisión:** El sistema se diseñará exclusivamente para consultas `SELECT` y peticiones HTTP `GET`.
- **Justificación:** Permitir `INSERT`, `UPDATE` o `DELETE` (SQL o API) vía lenguaje natural introduce un riesgo inaceptable de corrupción de datos y responsabilidad legal en un proyecto Open Source.

## 5. Integración API "Light Mode"

- **Decisión:** Usar `RequestsToolkit` crudo con inyección de resumen de Swagger en el System Prompt, en lugar de cargar `OpenAPIToolkit` completo.
- **Justificación:** Cargar el toolkit completo consumía demasiados tokens y tiempo de inicio. El modo ligero permite al agente entender qué endpoints existen (vía texto) e invocar una herramienta genérica `requests_get`, optimizando latencia y memoria.
- **Middleware de URL:** Se implementó una intercepción de `requests.get` para reescribir URLs relativas automáticamente, resolviendo la tendencia de los LLMs a omitir el dominio base.

## 6. Patrón Singleton para el Agente

- **Decisión:** Instanciar y compilar el grafo del agente (especialmente la sub-rutina de API) una sola vez al inicio (`__init__`).
- **Justificación:** La compilación del grafo de LangGraph tiene un costo computacional significativo (300ms+). Hacerlo por _request_ degradaba la experiencia de usuario. El patrón Singleton reduce la latencia de respuesta a <100ms.
