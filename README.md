# SQL Agent OSS

**Agente Híbrido SQL & API Open Source con Arquitectura Semántica y Aislamiento de Contexto** _Un sistema agéntico modular para convertir lenguaje natural a SQL de forma segura y consumir APIs dinámicamente._

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/poetry-package_manager-blueviolet)](https://python-poetry.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.0.x-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![Docker](https://img.shields.io/badge/Docker-Enabled-2496ED)](https://www.docker.com/)
[![Licencia: MIT](https://img.shields.io/badge/Licencia-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🎯 El Problema

Las herramientas tradicionales de "Text-to-SQL" fallan en entornos reales porque:

- **Alucinan nombres de columnas:** Adivinan nombres que no existen.
- **Ignoran el contexto del negocio:** No saben distinguir entre un "Ingreso Bruto" y "Neto".
- **Son inseguras:** Exponen credenciales o permiten inyecciones SQL.
- **Datos Estáticos:** Solo pueden ver lo que hay en la BD, perdiendo información en tiempo real que vive en APIs.

## ✨ La Solución: Arquitectura Híbrida y Desacoplada

Este proyecto implementa una arquitectura de **Sistema de IA Compuesto** que separa estrictamente:

1.  **Orquestación Híbrida (`src/`):** Router inteligente que decide entre consultar SQL o invocar herramientas API definidas en Swagger.
2.  **Configuración de Negocio (`config/`):** Definición de Modelos Lógicos de negocio.
3.  **Integración API (`docs/swagger.json`):** Definición agnóstica de herramientas externas.

### Características Clave

- **🚀 Arquitectura "Fast Agent" (v2.1):** Inicio instantáneo (<0.1s) gracias al patrón Singleton y "Light Mode" para herramientas API (sin parseo pesado de Swagger).
- **🛡️ Self-Healing SQL:** Bucle agéntico que atrapa errores de base de datos, analiza la sintaxis y reescribe la query automáticamente.
- **🔌 API Smart Wrapper:** Habilidad única de reescribir URLs relativas y manejar autenticación agnóstica para cualquier Swagger/OpenAPI.
- **🧠 Capa Semántica v2.5:** Define "Modelos Lógicos" en YAML que abstraen la complejidad física de las tablas para el negocio.
- **🚦 Router de Intención:** Clasifica preguntas en `DATABASE`, `API` o `GENERAL` para usar la herramienta óptima.
- **⚡ AsyncIO Nativo:** Núcleo 100% asíncrono para manejar alta concurrencia en I/O.
- **📱 Integración con WhatsApp:** Conexión vía WAHA para interacciones naturales, con memoria de conversaciones, indicadores de escritura y filtros de status. Ver [docs/05_whatsapp_integration.md](docs/05_whatsapp_integration.md).

## 🏗️ Estructura del Proyecto

El proyecto sigue una estructura profesional para facilitar la escalabilidad:

```text
.
├── config/                  # 🧠 CEREBRO: Configuración y Reglas de Negocio (YAML)
│   ├── business_context.yaml  # Contexto específico de la empresa (Modelos Lógicos)
│   └── settings.yaml          # Configuración técnica
├── data/                    # 💾 MEMORIA: Persistencia de datos
│   └── dictionary.yaml      # Diccionario Semántico generado
├── docs/
│   └── swagger.json         # 🔌 HERRAMIENTAS: Definición de APIs externas
├── src/                     # ⚙️ MOTOR: Código Fuente Puro
│   └── sql_agent/
│       ├── core/            # Router y Grafo (LangGraph)
│       ├── database/        # Drivers y Conexión Asíncrona
│       ├── api/             # Cargador dinámico de APIs
│       ├── semantic/        # Hidratación del Diccionario
│       └── config/          # Cargadores de Configuración
├── scripts/                 # 🚀 LANZADORES: Entrypoints
│   └── run_agent.py         # CLI Principal
```

## 🚀 Guía de Inicio Rápido

### 1. Prerrequisitos

- Python 3.11+
- [Poetry](https://python-poetry.org/docs/#installation)
- Docker (Opcional)

### 2. Instalación

```bash
# Clonar el repositorio
git clone https://github.com/tuusuario/sql-agent-oss.git
cd sql-agent-oss

# Instalar dependencias
poetry install
poetry shell
```

### 3. Configuración

Crea tu archivo de variables de entorno y define tanto la BD como la API opcional:

```bash
cp .env.example .env
# Edita DB_HOST, DB_USER, etc.
# Edita API_AUTH_HEADER y API_AUTH_VALUE si usas la integración Swagger
```

Define tu negocio en `config/business_context.yaml`.

### 4. Hidratación Semántica

El agente necesita compilar el conocimiento:

```bash
poetry run python scripts/generate_dictionary.py
```

### 5. Ejecutar Agente (CLI)

Interactúa con el agente desde la terminal:

```bash
poetry run python scripts/run_agent.py
```

## 🗺️ Roadmap

- [x] Conexión Asíncrona a BD
- [x] Arquitectura Híbrida (SQL + API)
- [x] Extracción de Esquema
- [x] Hidratación Semántica con IA
- [x] Bucle de Razonamiento (LangGraph)
- [x] Integración con WhatsApp (WAHA)
- [ ] Interfaz de Chat (Chainlit/Streamlit)
- [ ] Tests de integración API
- [ ] Migración a MCP para interoperabilidad

## 🤝 Contribución

Las PRs son bienvenidas. Por favor, asegúrate de no subir archivos de la carpeta `config/` o `data/` que contengan información sensible.
