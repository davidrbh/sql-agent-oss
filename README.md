# SQL Agent OSS

**Agente SQL Open Source con Arquitectura Semántica y Aislamiento de Contexto** _Un sistema agéntico modular para convertir lenguaje natural a SQL de forma segura y precisa._

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
- **Difíciles de mantener:** El código se mezcla con reglas de negocio específicas.

## ✨ La Solución: Arquitectura Desacoplada

Este proyecto implementa una arquitectura de **Sistema de IA Compuesto** que separa estrictamente:

1.  **Código Agnóstico (`src/`):** La lógica del agente, reutilizable para cualquier empresa.
2.  **Configuración de Negocio (`config/`):** Donde viven las reglas, el contexto y los prompts específicos.
3.  **Memoria de Datos (`data/`):** Donde persiste el conocimiento semántico.

### Características Clave

- **Capa Semántica Hidratada:** Generación automática de un `dictionary.yaml` enriquecido por IA.
- **Validación AST:** Uso de `sqlglot` para garantizar que el SQL generado es sintácticamente seguro.
- **Auto-Corrección:** Bucle agéntico (LangGraph) que corrige sus propios errores SQL.
- **Soporte Híbrido:** Funciona con Docker o con bases de datos locales (MySQL/PostgreSQL).

## 🏗️ Estructura del Proyecto

El proyecto sigue una estructura profesional para facilitar la escalabilidad:

```text
.
├── config/                  # 🧠 CEREBRO: Configuración y Reglas de Negocio (YAML)
│   ├── business_context.yaml  # Contexto específico de la empresa (No subir a Git)
│   └── settings.yaml          # Configuración técnica
├── data/                    # 💾 MEMORIA: Persistencia de datos
│   ├── dumps/               # Archivos .sql para inicialización
│   └── dictionary.yaml      # Diccionario Semántico generado
├── src/                     # ⚙️ MOTOR: Código Fuente Puro
│   └── sql_agent/
│       ├── core/            # Lógica del Grafo (LangGraph)
│       ├── database/        # Drivers y Conexión Asíncrona
│       ├── semantic/        # Hidratación del Diccionario
│       └── config/          # Cargadores de Configuración
├── logs/                    # 📝 AUDITORÍA: Logs de ejecución
└── scripts/                 # 🚀 LANZADORES: Entrypoints

```

## 🚀 Guía de Inicio Rápido

### 1. Prerrequisitos

- Python 3.11+
- [Poetry](https://www.google.com/search?q=https://python-poetry.org/docs/%23installation) (Gestor de paquetes)
- Docker (Opcional, si no tienes DB local)

### 2. Instalación

```bash
# Clonar el repositorio
git clone [https://github.com/tuusuario/sql-agent-oss.git](https://github.com/tuusuario/sql-agent-oss.git)
cd sql-agent-oss

# Instalar dependencias
poetry install

# Activar entorno virtual
poetry shell

```

### 3. Configuración

Crea tu archivo de variables de entorno:

```bash
cp .env.example .env
# Edita el .env con tus credenciales de OpenAI y Base de Datos

```

Define tu negocio en `config/business_context.yaml`:

```yaml
project_name: "Mi Empresa S.A."
business_context: |
  Somos una empresa de logística.
  Tabla crítica: 't_envios'.
  Estado 1 = Pendiente, Estado 2 = Entregado.
```

### 4. Hidratación Semántica (Primer Paso)

Antes de preguntar, el agente debe "aprender" tu base de datos:

```bash
poetry run python scripts/generate_dictionary.py

```

Esto generará el archivo `data/dictionary.yaml`.

### 5. Ejecutar Pruebas

Verifica que todo está conectado:

```bash
poetry run python scripts/test_schema.py

```

## 🗺️ Roadmap

- [x] Conexión Asíncrona a BD
- [x] Extracción de Esquema
- [x] Hidratación Semántica con IA
- [ ] Bucle de Razonamiento (LangGraph)
- [ ] Búsqueda Difusa de Entidades (Fuzzy Search)
- [ ] Interfaz de Chat (Chainlit)

## 🤝 Contribución

Las PRs son bienvenidas. Por favor, asegúrate de no subir archivos de la carpeta `config/` o `data/` que contengan información sensible.

```

***

```
