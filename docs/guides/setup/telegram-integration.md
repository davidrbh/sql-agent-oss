# Guía de Integración con Telegram

Este documento describe cómo configurar y poner en marcha el canal de comunicación de Telegram para interactuar con el agente. A diferencia de WhatsApp, Telegram utiliza un bot nativo basado en la librería `python-telegram-bot`, lo que simplifica la arquitectura al no requerir un gateway intermedio como WAHA.

## 1. Arquitectura y Flujo de Mensajes

La integración con Telegram se ejecuta como un servicio independiente dentro del ecosistema del agente:

-   **`telegram-bot`**: Un contenedor dedicado que ejecuta el script `src/channels/telegram/entry.py`. Este servicio utiliza **Polling**, lo que significa que el bot consulta activamente a los servidores de Telegram en busca de nuevos mensajes.

### Flujo de un Mensaje Entrante

1.  **Recepción:** El usuario envía un mensaje al bot de Telegram.
2.  **Polling:** El servicio `telegram-bot` descarga el mensaje desde los servidores de Telegram.
3.  **Invocación del Agente:** El script de Telegram inicializa el núcleo cognitivo (LangGraph) y le pasa el mensaje del usuario. El agente procesa la intención, ejecuta las herramientas necesarias (SQL o API) y genera una respuesta.
4.  **Respuesta al Usuario:** El bot utiliza el método `send_message` de Telegram para entregar la respuesta directamente al chat del usuario.

## 2. Configuración y Credenciales

Para que el bot funcione, necesitas obtener un Token oficial de Telegram.

### Obtener el Token (BotFather)

1.  En Telegram, busca al usuario `@BotFather`.
2.  Envía el comando `/newbot` y sigue las instrucciones para darle un nombre y un username a tu bot.
3.  Copia el **API Token** que te proporcionará (ej: `712345678:AAH...`).

### Configuración del Entorno

Asegúrate de configurar el token en tu archivo `.env`:

```bash
# Telegram Bot Token (Obtenido de @BotFather)
TELEGRAM_BOT_TOKEN=tu_telegram_token_aqui
```

El servicio está configurado en `docker-compose.yml` para usar este token automáticamente:

```yaml
  telegram-bot:
    container_name: telegram-bot
    command: python src/channels/telegram/entry.py
    environment:
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      # ... (otras variables)
```

## 3. Puesta en Marcha

1.  **Levanta los servicios:**
    ```bash
    docker compose up -d telegram-bot
    ```
2.  **Inicia la conversación:** Busca tu bot por su username en Telegram y presiona el botón **"Start"** o envía el comando `/start`.
3.  **Memoria de Conversación:** Actualmente, el bot de Telegram utiliza una memoria volátil en RAM (`user_histories`). Si el contenedor se reinicia, el contexto de la charla se perderá. (Nota: La migración a persistencia en PostgreSQL está planificada en el roadmap).

## 4. Características del Canal (UI/UX)

El canal de Telegram está configurado automáticamente mediante el catálogo de habilidades para ofrecer una experiencia optimizada:
-   Uso de **Markdown estándar** para legibilidad.
-   Listas cortas y directas.
-   Soporte para mensajes largos (división automática si superan los 4000 caracteres).

## 5. Troubleshooting (Solución de Problemas)

Si el bot no responde:

1.  **Verifica el Token:** Asegúrate de que `TELEGRAM_BOT_TOKEN` sea correcto y no tenga espacios adicionales en el archivo `.env`.
2.  **Revisa los logs:**
    ```bash
    docker compose logs -f telegram-bot
    ```
3.  **Conectividad:** Asegúrate de que el contenedor tiene salida a internet para conectar con `api.telegram.org`.
