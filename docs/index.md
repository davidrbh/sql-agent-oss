# Documentación de SQL Agent OSS (v4.0)

Bienvenido a la documentación oficial. Este proyecto sigue una arquitectura **SOA (Service-Oriented Architecture)** implementando el protocolo **MCP (Model Context Protocol)**.

## Estructura de la Documentación

La documentación está organizada siguiendo el estándar Diátaxis:

### 🧠 [Conceptos](./concepts/)
*Entiende el "por qué" y la filosofía del diseño.*
- [Arquitectura General (Hybrid Slice)](./concepts/architecture.md)
- [Capa Semántica y Seguridad](./concepts/semantic-layer.md)
- [Límites del Proyecto](./concepts/boundaries.md)

### 🚀 [Guías](./guides/)
*Tutoriales paso a paso para configurar y extender.*
- **Setup:**
    - [Integración con WhatsApp](./guides/setup/whatsapp-integration.md)
    - [Configuración de Terminal WARP](./guides/setup/warp-terminal.md)
- **Desarrollo:**
    - [Cómo Extender el Agente](./guides/development/extending-the-agent.md)
    - [Personalizar la UI (Chainlit)](./guides/development/chainlit-ui.md)

### 📚 [Referencia](./reference/)
*Especificaciones técnicas detalladas.*
- [Configuración de Infraestructura](./reference/config/infrastructure.md)
- [API Swagger](./reference/api/swagger.json)
- [Módulos del Core](./reference/agent-core.md)

### 🏛️ [ADR (Architecture Decision Records)](./adr/)
*Historial de decisiones técnicas importantes.*
- [0001: Stack Tecnológico](./adr/0001-tech-stack.md)
- [0002: Roadmap de Modernización v3](./adr/0002-modernization-roadmap-v3.md)

---

## Búsqueda Rápida

- ¿Quieres entender cómo funciona la seguridad SQL? Lee [Semantic Layer](./concepts/semantic-layer.md).
- ¿Quieres conectar una API nueva? Lee [Extending the Agent](./guides/development/extending-the-agent.md).
