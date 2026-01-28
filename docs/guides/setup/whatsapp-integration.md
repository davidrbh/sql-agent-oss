# Guía de Integración con WhatsApp (vía WAHA)

Este documento describe cómo el proyecto se integra con WhatsApp para permitir a los usuarios interactuar con el agente a través de mensajería. La integración se realiza utilizando [WAHA (WhatsApp HTTP API)](https://waha.devlike.pro/), una solución robusta que actúa como un puente entre la API de WhatsApp y nuestra aplicación.

## 1. Arquitectura y Flujo de Mensajes

A partir de la **v4.3**, el proyecto utiliza el motor **NOWEB** de WAHA. A diferencia de las versiones anteriores que emulaban un navegador Chrome (WEBJS), NOWEB se conecta directamente a los servidores de WhatsApp mediante WebSockets.

**Ventajas de NOWEB:**
-   **Estabilidad:** Elimina errores de "navegador desconectado" o cuelgues de Puppeteer.
-   **Rendimiento:** Reduce el consumo de memoria RAM en un 60% y la carga de CPU.
-   **Velocidad:** Las notificaciones de mensajes son casi instantáneas.

La arquitectura se basa en la comunicación entre dos servicios principales:

-   **`waha`**: El servicio Docker que se conecta directamente a los servidores de WhatsApp y expone una API REST para enviar y recibir mensajes.
-   **`agent-host`**: Nuestro servidor principal, que contiene la lógica del agente y un endpoint para recibir los webhooks de `waha`.

### Flujo de un Mensaje Entrante

1.  **Recepción:** Un usuario envía un mensaje al número de WhatsApp vinculado a `waha`.
2.  **Webhook:** El servicio `waha` recibe el mensaje. Gracias a la configuración en `docker-compose.yml`, `waha` sabe que debe notificar a nuestro agente. Para ello, realiza una petición `POST` a la URL definida en la variable de entorno `WHATSAPP_WEBHOOK_URL` (ej: `http://agent-host:8000/whatsapp/webhook`).
3.  **Enrutamiento:** El `agent-host` recibe esta petición en su API (definida en `src/api/server.py`) y la enruta internamente al router de WhatsApp (`src/channels/whatsapp/router.py`).
4.  **Procesamiento en Segundo Plano:** Para asegurar una respuesta rápida y evitar timeouts, el router de WhatsApp valida el mensaje y delega su procesamiento a una **tarea en segundo plano** (`BackgroundTasks` de FastAPI). Esto permite al servidor responder inmediatamente a `waha` con un `200 OK`.
5.  **Invocación del Agente:** La tarea en segundo plano (`process_message`) invoca el grafo de LangGraph, pasándole el contenido del mensaje del usuario. El agente piensa, genera el SQL, lo ejecuta y formula una respuesta.
6.  **Respuesta al Usuario:** Una vez que el agente tiene la respuesta final, la misma tarea en segundo plano utiliza la API de `waha` para enviar el mensaje de vuelta al chat del usuario original.

## 2. Configuración Simplificada

La configuración es automática y se gestiona casi en su totalidad a través de variables de entorno en el `docker-compose.yml` y tu archivo `.env`. **Ya no es necesario configurar webhooks manualmente con cURL.**

### Archivo `docker-compose.yml`

Observa la sección del servicio `waha`. La variable clave es `WHATSAPP_WEBHOOK_URL`:

```yaml
  # La Boca (WhatsApp HTTP API - WAHA)
  waha:
    image: devlikeapro/waha:latest
    ports:
      - "3001:3000" # Dashboard en puerto 3001
    env_file:
      - .env
    environment:
      # URL donde WAHA enviará los mensajes recibidos
      - WHATSAPP_WEBHOOK_URL=http://agent-host:8000/whatsapp/webhook
      # ... (otras variables)
```
Esta línea le instruye a `waha` que envíe todos los eventos de mensajes entrantes directamente a nuestro `agent-host`.

### Archivo `.env`

Asegúrate de configurar las credenciales de seguridad para `waha` en tu archivo `.env`, tal como se define en `.env.example`:

```bash
# Credenciales para el dashboard y la API de WAHA
WAHA_API_KEY=tu_clave_secreta
WHATSAPP_SWAGGER_USERNAME=admin
WHATSAPP_SWAGGER_PASSWORD=admin
```

## 3. Puesta en Marcha (Conexión por QR)

1.  **Levanta los servicios:**
    ```bash
    docker-compose up -d
    ```
2.  **Accede al Dashboard de WAHA:** Abre tu navegador y ve a `http://localhost:3001`. Podrás ver la interfaz de Swagger para la API de WAHA.
3.  **Inicia una sesión y escanea el QR:** Utiliza la interfaz de Swagger o una herramienta como Postman para hacer una petición `POST` al endpoint `/api/sessions/start` con el body `{"name": "default"}`. Luego, haz una petición `GET` a `/api/sessions/default/qr` para obtener el código QR. Escanéalo con la app de WhatsApp en tu teléfono (`Dispositivos vinculados` > `Vincular un dispositivo`).
4.  **Persistencia de Sesión:** La sesión de WhatsApp se guarda en el volumen `waha_sessions` definido en `docker-compose.yml`, por lo que **no necesitarás escanear el QR cada vez** que reinicies los contenedores.

## 4. Estado de la Memoria de Conversaciones

La arquitectura del `agent-host` con LangGraph está diseñada para soportar memoria persistente entre conversaciones. El grafo principal (`agent_core/graph.py`) ya acumula mensajes en su estado.

Sin embargo, la implementación actual del canal de WhatsApp en `channels/whatsapp/router.py` inicia una nueva invocación del grafo para cada mensaje entrante, por lo que **no hay memoria a largo plazo entre mensajes distintos del mismo usuario**.

Habilitar esta funcionalidad es el siguiente paso lógico y requeriría integrar un **Checkpointer** de LangGraph (como `SqliteSaver` o `RedisSaver`) en la función `process_message`, utilizando el `chat_id` como el identificador del hilo de conversación (`thread_id`).

## 5. Troubleshooting (Solución de Problemas)

Si el agente no responde a los mensajes de WhatsApp:

1.  **Revisa los logs del `agent-host`:** Es el lugar más probable para encontrar errores, ya sea en la recepción del webhook o durante la ejecución del agente.
    ```bash
    docker-compose logs -f agent-host
    ```
2.  **Revisa los logs de `waha`:** Para ver si `waha` está recibiendo los mensajes de WhatsApp y si está enviando el webhook correctamente al `agent-host`.
    ```bash
    docker-compose logs -f waha
    ```
3.  **Verifica el estado de la sesión en WAHA:** Asegúrate de que el estado sea `CONNECTED`. Puedes hacerlo desde el dashboard en `http://localhost:3001` con el endpoint `GET /api/sessions/default/status`.