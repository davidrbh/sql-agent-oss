# Visión General de la Arquitectura & Filosofía de Diseño v2

## 1. Introducción

**SQL Agent OSS** ha evolucionado hacia un **Sistema de Inteligencia Artificial Compuesto Híbrido**. Ya no se limita a traducir texto a SQL, sino que actúa como un orquestador inteligente capaz de decidir cuándo consultar la base de datos analítica y cuándo consumir APIs operacionales en tiempo real.

El objetivo es resolver la necesidad empresarial de tener una interfaz unificada para datos históricos (SQL) y datos en tiempo real (APIs).

## 2. El Problema Ampliado

Los enfoques tradicionales de "Text-to-SQL" tienen un límite duro: la base de datos a menudo contiene datos "fríos" o históricos.

- ¿Cuántas ventas hice ayer? -> SQL (Correcto)
- ¿Cuál es el estado actual del envío #123? -> SQL (Posiblemente desactualizado) vs API (Tiempo real).
- ¿Cómo cancelo el pedido #999? -> SQL (PELIGROSO/IMPOSIBLE) vs API (Correcto).

## 3. La Solución: Arquitectura Híbrida con Router

Implementamos un **Grafo de Estado (StateGraph)** orquestado por LangGraph que introduce un "Córtex Prefrontal" (Router) antes de cualquier acción.

### Diagrama de Flujo Lógico

```mermaid
graph TD
    User[👤 Usuario] -->|Pregunta| Router{🚦 Router de Intención}

    Router -->|Intención: DATABASE| SqlBranch[📂 Rama SQL]
    Router -->|Intención: API| ApiBranch[🔌 Rama API]
    Router -->|Intención: GENERAL| ChatBranch[💬 Rama Conversacional]

    subgraph "Rama SQL (Análisis)"
        SqlBranch --> Planner[🧠 Planificador]
        Planner --> Generator[✍️ Generador SQL]
        Generator --> Validator[🛡️ Guardrails (SQLGlot)]
        Validator --> Executor[impar Database]
        Executor -->|Error| RetryLoop[🔄 Bucle de Auto-Corrección]
        RetryLoop --> Generator
    end

    subgraph "Rama API (Operacional)"
        ApiBranch --> ToolLoader[📦 Cargador OpenAPI]
        ToolLoader --> ToolExec[🛠️ Ejecutor de Herramienta]
    end

    Executor --> Synthesizer[📝 Sintetizador de Respuesta]
    ToolExec --> Synthesizer
    ChatBranch --> Synthesizer

    Synthesizer --> User
```

### Componentes Core Actualizados

#### A. Router de Intención (El Cerebro)

Es el primer nodo del grafo. Utiliza un LLM con few-shot prompting para clasificar la consulta en:

- `DATABASE`: Preguntas analíticas, conteos, reportes.
- `API`: Consultas de estado, acciones específicas, datos en vivo.
- `GENERAL`: Saludos, dudas fuera de dominio.

#### B. Capa Semántica V2.5 (Hydrator)

Combina dos fuentes de verdad para crear el contexto:

1.  **Esquema Físico:** Introspección directa de la BD (`Inspector`).
2.  **Contexto de Negocio:** Archivo `config/business_context.yaml` donde se definen "Modelos Lógicos" que agrupan tablas físicas.

#### C. Cargador Universal de API

Módulo que convierte dinámicamente una especificación `swagger.json` en herramientas ejecutables para el agente.

- **Autenticación Agnóstica:** Inyecta headers definidos en variables de entorno (`API_AUTH_HEADER`), permitiendo conectar cualquier API REST estándar sin cambiar el código fuente.

#### D. Motor Asíncrono

Se mantiene el uso de `asyncio` para todas las operaciones I/O (DB y HTTP Requests), garantizando alta concurrencia.

## 4. Stack Tecnológico

- **Orquestador:** LangGraph (State Machines)
- **LLM:** DeepSeek / OpenAI (Configurable vía Factory)
- **Integración API:** OpenAPIToolkit + RequestsWrapper
- **Base de Datos:** SQLAlchemy Async + Drivers nativos
- **Interfaz:** CLI (Script Python) actualmente, extensible a Web.

## 5. Estrategia de Seguridad

- **SQL:** Validación AST estricta (solo `SELECT`, bloqueo de DML).
- **API:** Limitación de endpoints expuestos vía `swagger.json` (solo incluir endpoints seguros/lectura si se desea).
- **Control:** El agente opera en modo "Read-Only" por defecto a menos que se configure explícitamente lo contrario.

## 6. Optimizaciones y Robustez (v2.1)

En la última iteración, se implementaron mejoras críticas para velocidad y resiliencia:

### A. Patrón Singleton & "Light Mode" (Velocidad)

- **Problema:** Inicializar las herramientas de API (langchain toolkit) tomaba 3-5 segundos por consulta debido al parseo masivo del Swagger.
- **Solución:** Se implementó carga única al inicio (`__init__`) y un "Light Mode" que inyecta un resumen de texto en el Prompt del sistema ("Memory Cache") en lugar de cargar todas las herramientas como objetos pesados.
- **Resultado:** Latencia de inicio reducida a < 0.1s.

### B. Mecanismo Self-Healing SQL (Resiliencia)

- **Problema:** Los LLMs a veces alucinan nombres de columnas (ej: `user_id` vs `users_id`) o sintaxis ambigua.
- **Solución:** Si la ejecución SQL falla, el grafo captura la excepción, la analiza e inyecta el mensaje de error real de la base de datos de vuelta al LLM con un prompt de "Modo Corrección".
- **Flujo:** `Generar -> Fallar -> Leer Error -> Reflexionar -> Re-Generar -> Éxito`.

### C. Manejo Inteligente de API

- **URL Rewriting:** Middleware que intercepta URLs relativas (ej: `/admin/users`) y les antepone el dominio base automáticamente, evitando errores comunes de los LLMs.
- **Anti-Alucinación de Metadatos:** Reglas estrictas que prohíben ejecutar herramientas HTTP para preguntas de "descubrimiento" (ej: "¿Qué endpoints hay?"), forzando el uso de la memoria interna (Swagger Summary).

## 7. Roadmap hacia MCP (Model Context Protocol)

El siguiente paso evolutivo es migrar las herramientas "hardcodeadas" a servidores MCP estándar, desacoplando completamente la lógica del agente de los drivers de base de datos y clientes HTTP.
