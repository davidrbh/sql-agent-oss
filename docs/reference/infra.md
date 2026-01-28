# Infraestructura y Resiliencia

El sistema utiliza una arquitectura de micro-servicios (Sidecars) para garantizar el aislamiento y la escalabilidad.

## 1. Conectividad MCP (Model Context Protocol)

El corazón de la infraestructura es el `MultiServerMCPClient`, que gestiona múltiples sesiones concurrentes hacia los sidecars.

::: infra.mcp.multi_server_client
    handler: python

## 2. Motor de WhatsApp (WAHA NOWEB)

A diferencia de las versiones anteriores basadas en Puppeteer, la **v4.3** utiliza el motor **NOWEB**.

*   **Arquitectura:** Basada en WebSocket puro.
*   **Ventajas:** 
    *   No requiere Chromium (Ahorro del 60% de RAM).
    *   Conexión persistente más estable.
    *   Auto-configuración de Webhooks al arrancar el Agente Host.

## 3. Optimización de Base de Datos

El sidecar MySQL (`mcp-mysql-sidecar`) está configurado para entornos de **Producción con DB Remota**:

*   **Pool de Conexiones:** 30 conexiones simultáneas.
*   **Queueing:** Encolamiento infinito para evitar errores de saturación en WhatsApp.
*   **Idle Timeout:** 60 segundos para reutilización eficiente de túneles de red.