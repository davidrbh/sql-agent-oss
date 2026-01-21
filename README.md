# SQL Agent OSS

**Agente Híbrido SQL & API Open Source con Arquitectura Semántica y Aislamiento de Contexto**

_Un sistema agéntico modular para convertir lenguaje natural a SQL de forma segura y consumir APIs dinámicamente, diseñado para la escalabilidad y flexibilidad._

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/poetry-package_manager-blueviolet)](https://python-poetry.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.0.x-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![Docker](https://img.shields.io/badge/Docker-Enabled-2496ED)](https://www.docker.com/)
[![Licencia: MIT](https://img.shields.io/badge/Licencia-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 🎯 El Problema

Las herramientas tradicionales de "Text-to-SQL" y agentes conversacionales fallan en entornos reales porque:

- **Alucinan nombres de columnas:** Generan SQL incorrecto o a partir de supuestos erróneos.
- **Ignoran el contexto del negocio:** No comprenden la semántica detrás de los datos.
- **Son inseguras:** Exponen credenciales o permiten inyecciones SQL.
- **Datos Estáticos:** Solo pueden ver lo que hay en la BD, perdiendo información en tiempo real que vive en APIs.
- **Falta de Modularidad:** Dificultan la incorporación de nuevos canales o funcionalidades.

## ✨ La Solución: Arquitectura Híbrida de Micro-Agentes (Hybrid Slice)

Este proyecto implementa una arquitectura de **Sistema de IA Compuesto** con un enfoque modular "Hybrid Slice", que desacopla y orquesta distintos componentes inteligentes:

- **Agente Principal (Cerebro):** Orquesta el flujo de trabajo, decide cuándo usar SQL o llamar APIs.
- **Sidecar de Base de Datos (Brazo):** Ejecuta consultas SQL de forma segura y aislada.
- **Gateway de Canales (Boca):** Maneja la comunicación con usuarios a través de diferentes plataformas (WhatsApp, UI web).

### Características Clave

- **🚀 Arquitectura "Hybrid Slice":** Un enfoque modular que permite extender fácilmente el agente con nuevas fuentes de datos (SQL, APIs) y canales de comunicación.
- **🛡️ Self-Healing SQL:** El agente es capaz de identificar y corregir errores en las consultas SQL generadas, iterando hasta obtener un resultado válido.
- **🔌 API Smart Wrapper:** Habilidad para invocar APIs externas definidas en Swagger/OpenAPI, gestionando la autenticación y reescribiendo URLs automáticamente.
- **🧠 Capa Semántica Enriquecida:** Definición de "Modelos Lógicos" en YAML que abstraen la complejidad física de la base de datos, proveyendo al agente un contexto de negocio claro.
- **🚦 Router de Intención Inteligente:** Clasifica las preguntas del usuario para dirigir eficientemente la consulta hacia la base de datos (análisis histórico), APIs (estado en tiempo real) o una respuesta general.
- **⚡ Núcleo Asíncrono:** Desarrollado con LangGraph y `asyncio` para una alta concurrencia y rendimiento en operaciones de I/O.
- **📱 Soporte Multicanal:** Interacción con usuarios a través de una interfaz web (Chainlit), canales de mensajería (WhatsApp vía WAHA) y **Telegram**.
- **⚙️ Protocolo MCP (Model Context Protocol):** Comunicación estandarizada y segura entre el agente principal y los sidecars de herramientas.

## 🏗️ Estructura del Proyecto

Este proyecto sigue una arquitectura monorepo, organizando los componentes de manera lógica para facilitar la escalabilidad y el desarrollo:

```
.
├── apps/                    # Aplicaciones principales del ecosistema
│   └── agent-host/            # El "Cerebro": Servidor del agente y UI web (Python)
├── services/                # Servicios de soporte (Sidecars)
│   └── mcp-mysql-sidecar/     # El "Brazo": Proxy seguro para ejecutar SQL (Node.js/TypeScript)
├── config/                  # Configuraciones globales del proyecto
│   ├── business_context.yaml  # 🧠 Capa Semántica: Reglas y Modelos de Negocio
│   └── settings.yaml          # Configuración técnica del sistema
├── data/                    # Datos persistentes y logs
├── docs/                    # 📚 Documentación detallada del proyecto
├── docker-compose.yml       # Orquestación de todos los servicios vía Docker
├── .env.example             # Plantilla para variables de entorno
└── scripts/                 # Scripts de utilidad
```

Para una explicación detallada de la arquitectura, consulta [docs/01_architecture/overview.md](./docs/01_architecture/overview.md).

## 🚀 Guía de Inicio Rápido (Docker Compose)

La forma recomendada para levantar el proyecto completo es usando Docker Compose.

### 1. Prerrequisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop) (o Docker Engine y Docker Compose) instalado.
- Un editor de texto.

### 2. Configuración del Entorno

1.  **Clona el repositorio:**
    ```bash
    git clone https://github.com/tu_usuario/sql-agent-oss.git
    cd sql-agent-oss
    ```
2.  **Crea tu archivo de variables de entorno:**
    ```bash
    cp .env.example .env
    ```
3.  **Edita el archivo `.env`:**
    - Configura los detalles de tu base de datos MySQL (ej. `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`).
    - Si utilizas la integración con APIs externas y requieren autenticación, configura `API_AUTH_HEADER` y `API_AUTH_VALUE`.
    - Si vas a usar la integración con WhatsApp, configura las variables `WAHA_*`.
    - Asegúrate de configurar `DEEPSEEK_API_KEY` o tu clave para el LLM que estés utilizando.

### 3. Levantando los Servicios

Construye y levanta todos los servicios definidos en `docker-compose.yml`:

```bash
docker-compose up --build -d
```

Esto iniciará:

- `mcp-mysql`: El sidecar para la base de datos.
- `agent-host`: El servidor del agente (FastAPI) y la interfaz web (Chainlit).
- `telegram-bot`: El bot de Telegram (si está configurado).
- `waha`: El gateway para WhatsApp (si está configurado).

### 4. Accede al Agente

Una vez que los contenedores estén corriendo:

- **Interfaz Web (Chainlit):** Abre tu navegador y ve a `http://localhost:8000`.
- **API del Agente:** La API REST principal del agente estará disponible en `http://localhost:8000/docs` (documentación Swagger UI).
- **Bot de Telegram:** Busca tu bot en Telegram y envíale un mensaje para interactuar (requiere `TELEGRAM_BOT_TOKEN` en `.env`).
- **WAHA Dashboard (Opcional):** Si configuraste WhatsApp, el dashboard de WAHA estará en `http://localhost:3001`.

### 5. Configuración Semántica (Primer uso del Agente)

Para que el agente entienda tu negocio, necesitas generar el diccionario semántico:

- Accede al contenedor `agent-host`:
  ```bash
  docker exec -it <ID_DEL_CONTENEDOR_AGENT_HOST> bash
  # Puedes obtener el ID del contenedor con 'docker ps'
  ```
- Dentro del contenedor, ejecuta el script de generación del diccionario:
  ```bash
  poetry run python scripts/generate_dictionary.py
  exit
  ```
  _(Nota: Este paso solo es necesario si tu `business_context.yaml` cambia o es la primera vez que lo configuras.)_

---

## 📚 Documentación Detallada

Para una comprensión más profunda del proyecto, su arquitectura, cómo extenderlo y configurar características avanzadas, explora la carpeta [`docs/`](./docs).

## 🤝 Contribución

Las contribuciones son bienvenidas. Por favor, consulta `CONTRIBUTING.md` para más detalles.
Asegúrate de no subir archivos de configuración (`.env`, `config/*.yaml` sensibles) ni datos privados (`data/`) a tu repositorio.

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Consulta el archivo `LICENSE` para más detalles.
