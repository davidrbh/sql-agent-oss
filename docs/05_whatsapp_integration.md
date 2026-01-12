# Integración con WhatsApp (WAHA - WhatsApp HTTP API)

Esta guía explica cómo conectar tu Agente SQL con WhatsApp utilizando [WAHA (WhatsApp HTTP API)](https://waha.devlike.pro/), una alternativa estable y ligera a Evolution API. Incluye soporte para memoria de conversaciones, indicadores de escritura, y filtros para evitar respuestas a status updates.

## 1. Arquitectura

Hemos desplegado un entorno con los siguientes contenedores:

- `waha`: El motor que se conecta a los servidores de WhatsApp via WebJS o Noweb.
- `agent-bridge`: Un servidor intermedio (Python/FastAPI) que recibe los mensajes de WhatsApp, maneja memoria y contextos, y los pasa al Agente SQL.
- `mysql`: Base de datos para el agente (opcional para persistencia de sesiones).

El flujo es: WhatsApp → WAHA → Webhook → Agent Bridge → LangGraph Agent → Respuesta a WhatsApp.

## 2. Puesta en Marcha

1. Levanta los servicios con Docker Compose:

   ```bash
   docker compose up -d
   ```

2. Verifica que WAHA esté corriendo:
   - Accede a `http://localhost:3001/docs` para la documentación Swagger de WAHA.
   - Deberías ver endpoints como `/api/sessions` y `/api/sendText`.

## 3. Conectar tu Número (QR Code)

WAHA usa sesiones para manejar conexiones. Crea una sesión y escanea el QR.

### Paso A: Crear Sesión

Ejecuta este comando (usa Postman, curl o la interfaz web):

```bash
curl -X POST http://localhost:3001/api/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "name": "default",
    "start": true
  }'
```

Esto inicia la sesión "default" y genera un QR.

### Paso B: Escanear QR

Obtén el QR desde la API:

```bash
curl http://localhost:3001/api/sessions/default/qr
```

Te devolverá una imagen en base64 o una URL. Escanéala con tu celular (WhatsApp → Dispositivos Vinculados → Vincular Dispositivo).

Una vez conectado, el status cambiará a "CONNECTED".

## 4. Configurar el Webhook

Configura WAHA para enviar mensajes al bridge del agente:

```bash
curl -X POST http://localhost:3001/api/webhooks \
  -H "Content-Type: application/json" \
  -d '{
    "url": "http://agent-bridge:8001/webhook",
    "events": ["message"],
    "session": "default"
  }'
```

El bridge maneja la autenticación y filtra mensajes (e.g., ignora status@broadcast para evitar respuestas a stories).

## 5. Características Avanzadas

### Memoria de Conversaciones

- El agente mantiene contexto entre mensajes usando LangGraph MemorySaver.
- Soporta resets manuales (e.g., "reinicia conversación") para limpiar estado.
- Inyecta historial en prompts de SQL para mejorar precisión (e.g., referencias como "y los activos?").

### Indicadores de Escritura (Typing)

- El bridge envía indicadores de "escribiendo..." mientras el agente procesa.
- Mejora la UX en WhatsApp, simulando respuestas humanas.

### Filtros y Seguridad

- Filtra mensajes de status para evitar respuestas automáticas a updates.
- Webhook protegido con secrets (configurado en `.env`).

## 6. Configuración en `.env`

Asegúrate de tener estas variables en tu `.env`:

```bash
WAHA_BASE_URL=http://waha:3001
WAHA_API_KEY=tu_api_key_aqui  # Si WAHA requiere autenticación
WEBHOOK_SECRET=tu_secret_seguro
```

## 7. Troubleshooting

Si el agente no responde:

1. Revisa logs del bridge: `docker compose logs -f agent-bridge`
2. Revisa logs de WAHA: `docker compose logs -f waha`
3. Verifica conexión: `curl http://localhost:3001/api/sessions/default/status`
4. Para issues de memoria: Asegúrate de que `MemorySaver` esté habilitado en `graph.py`.
5. Si hay loops infinitos: Reinicia contenedores y verifica volúmenes de sesiones.

Para más detalles, consulta la [documentación de WAHA](https://waha.devlike.pro/).
