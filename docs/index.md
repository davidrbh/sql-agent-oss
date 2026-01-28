# SQL Agent OSS v4.3 (SOA Ready) 🚀

Bienvenido a la documentación oficial del **SQL Agent OSS**, el ecosistema de inteligencia empresarial más avanzado, seguro y rápido para entornos Fintech.

## 🏗️ Filosofía del Proyecto

Esta no es una aplicación monolítica. Es una **Arquitectura de Micro-Agentes** basada en el protocolo **MCP (Model Context Protocol)**. El "Cerebro" (Agent Host) razona y planifica, mientras que los "Músculos" (Sidecars) ejecutan tareas específicas en entornos aislados.

## ✨ Características de v4.3 (High Performance)

*   **⚡ Latencia Ultra-Baja:** Optimizaciones de *Parallel Tool Execution* y *DeepSeek Prompt Caching*.
*   **📱 WhatsApp Industrial:** Motor **NOWEB** integrado para máxima estabilidad y bajo consumo.
*   **🛡️ Seguridad AST:** Motor **SQLGuard** que valida cada consulta a nivel sintáctico antes de su ejecución.
*   **🔌 Multi-Servicio:** Capacidad nativa para consultar Bases de Datos y APIs REST simultáneamente.
*   **💾 Memoria Infinita:** Persistencia en PostgreSQL que permite mantener el contexto incluso tras reinicios.
*   **🎨 Configuración Cognitiva:** Personalidad y habilidades 100% configurables vía YAML.

## 🚀 Guía Rápida de Inicio

1.  **Configura tu entorno:** Renombra `.env.example` a `.env` y añade tus credenciales.
2.  **Levanta la infraestructura:**
    ```bash
    docker compose up -d
    ```
3.  **Vincula WhatsApp:** Entra a `http://localhost:3001` y escanea el QR.
4.  **¡Empieza a preguntar!**

---

*Desarrollado con ❤️ para ecosistemas de datos modernos.*