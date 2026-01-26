# Documentación de SQL Agent OSS (v4.0)

Bienvenido a la documentación oficial. Este proyecto sigue una arquitectura **SOA (Service-Oriented Architecture)** implementando el protocolo **MCP (Model Context Protocol)**.

## Estructura de la Documentación

La documentación está organizada siguiendo el estándar Diátaxis:

### 🧠 [Conceptos](./concepts/)
*Entiende el "por qué" y la filosofía del diseño.*
- [Arquitectura General (Hybrid Slice)](./concepts/architecture.md)
- [Capa Semántica y Seguridad](./concepts/semantic_layer.md)
- [Límites del Proyecto](./concepts/boundaries.md)

### 🚀 [Guías](./guides/)
*Tutoriales paso a paso para configurar y extender.*
- **Setup:**
    - [Integración con WhatsApp](./guides/setup/whatsapp_integration.md)
    - [Configuración de Terminal WARP](./guides/setup/warp_terminal.md)
- **Desarrollo:**
    - [Cómo Extender el Agente](./guides/development/extending_the_agent.md)
    - [Personalizar la UI (Chainlit)](./guides/development/chainlit_ui.md)

### 📚 [Referencia](./reference/)
*Especificaciones técnicas detalladas.*
- [Configuración de Infraestructura](./reference/config/infrastructure.md)
- [API Swagger](./reference/api/swagger.json)
- [Módulos del Core](./reference/agent_core.md)

### 🏛️ [ADR (Architecture Decision Records)](./adr/)
*Historial de decisiones técnicas importantes.*
- [001: Stack Tecnológico](./adr/001_tech_stack.md)
- [002: Roadmap de Modernización v3](./adr/002_modernization_roadmap_v3.md)

---

## Búsqueda Rápida

- ¿Quieres instalarlo? Ve al [README](../README.md).
- ¿Quieres entender cómo funciona la seguridad SQL? Lee [Semantic Layer](./concepts/semantic_layer.md).
- ¿Quieres conectar una API nueva? Lee [Extending the Agent](./guides/development/extending_the_agent.md).
