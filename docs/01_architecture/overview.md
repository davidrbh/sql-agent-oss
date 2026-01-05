# Visión General de la Arquitectura & Filosofía de Diseño

## 1. Introducción
**SQL Agent OSS** es un sistema de Inteligencia Artificial Compuesto (Compound AI System) diseñado para la generación y ejecución segura de SQL en entornos empresariales. A diferencia de los enfoques tradicionales de "Chat-con-tu-DB" que conectan un LLM directamente a la base de datos, este proyecto implementa una arquitectura de **Agentes Cognitivos** interpuesta por una **Capa Semántica**.

El objetivo no es solo traducir texto a SQL, sino garantizar que la ejecución sea:
1.  **Semánticamente Correcta:** Alineada con las definiciones de negocio (KPIs).
2.  **Operativamente Segura:** Imposibilidad técnica de realizar operaciones destructivas.
3.  **Escalable:** Basada en I/O asíncrono para alta concurrencia.

## 2. El Problema: Por qué fallan los enfoques ingenuos
La investigación preliminar ("La Ilusión de la Simplicidad") identificó tres puntos de fallo críticos en los prototipos estándar:
* **Brecha Semántica:** Los LLMs no entienden que `t1_col5` significa "Ingresos Netos".
* **Alucinaciones de Esquema:** Los modelos inventan tablas o columnas que no existen.
* **Riesgos de Seguridad:** La inyección de prompts puede derivar en exfiltración o destrucción de datos.

## 3. La Solución: Arquitectura de Sistema Compuesto
Para mitigar estos riesgos, **SQL Agent OSS** no utiliza una cadena lineal, sino un **Grafo de Estado (StateGraph)** orquestado por LangGraph. El flujo de información pasa por múltiples etapas de validación antes de tocar la base de datos.

### Diagrama de Alto Nivel
El sistema sigue el patrón "Planificar - Recuperar - Generar - Validar - Ejecutar".



### Componentes Core

#### A. Capa Semántica Viva (The Living Semantic Layer)
En lugar de pasar el esquema crudo (DDL) al LLM, el sistema utiliza un **Diccionario de Datos Enriquecido**.
* **Hidratación Automática:** Scripts (`scripts/generate_dictionary.py`) que utilizan un LLM para describir tablas y columnas automáticamente, detectando relaciones implícitas.
* **Búsqueda Difusa de Valores:** Un sistema de recuperación (`thefuzz`) que intercepta entidades (ej: "pepsi") y las mapea a su valor real en base de datos ("PepsiCo Intl") antes de generar el SQL.

#### B. Orquestación Agéntica (LangGraph)
El cerebro del sistema es un grafo cíclico que permite la **Autocorrección (Self-Correction)**.
* Si el SQL generado falla (ej: error de sintaxis), el agente captura el error, razona sobre él y reintenta la generación hasta 3 veces.
* Esto eleva la tasa de éxito (Execution Accuracy) drásticamente comparado con sistemas "one-shot".

#### C. Seguridad en Profundidad (Zero Trust)
La seguridad no es una característica opcional, es estructural.
* **Validación AST (SQLGlot):** Cada consulta generada se analiza sintácticamente. Si el Árbol de Sintaxis Abstracta contiene nodos prohibidos (`DROP`, `DELETE`, `UPDATE`, `GRANT`), la ejecución se bloquea antes de llegar a la red.
* **Infraestructura Read-Only:** La conexión a la base de datos se realiza estrictamente con credenciales de solo lectura.

#### D. Motor Asíncrono
Todo el pipeline, desde la API del LLM hasta la consulta a PostgreSQL, utiliza `asyncio`.
* Drivers: `asyncpg` y `SQLAlchemy (AsyncEngine)`.
* Beneficio: Permite manejar cientos de consultas concurrentes sin bloquear el hilo principal de Python.

## 4. Stack Tecnológico (Filosofía FOSS)
El proyecto se construye sobre tecnologías 100% Open Source, con la única excepción de la API de inferencia (OpenAI/Anthropic).

* **Lenguaje:** Python 3.11+
* **Orquestador:** LangChain / LangGraph
* **Base de Datos:** PostgreSQL (Soporte para MySQL vía `aiomysql`)
* **Motor de Búsqueda:** ChromaDB (Vectorial) + TheFuzz (Lexical)
* **Interfaz:** Chainlit
* **Gestión de Dependencias:** Poetry

## 5. Estrategia de Evaluación
La calidad se mide mediante **Precisión de Ejecución (Execution Accuracy)**. Mantenemos un "Golden Dataset" (pares de Pregunta/SQL Correcto) y utilizamos contenedores efímeros (`testcontainers`) para validar que el agente produce los mismos *datos* que la consulta de referencia, independientemente de cómo escriba el SQL.
