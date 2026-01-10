# Integración con WhatsApp (Evolution API)

Esta guía explica cómo conectar tu Agente SQL con WhatsApp utilizando [Evolution API](https://github.com/EvolutionAPI/evolution-api).

## 1. Arquitectura

Hemos desplegado un entorno con los siguientes contenedores nuevos:

- `evolution_api`: El motor que se conecta a los servidores de WhatsApp.
- `whatsapp_bridge`: Un servidor intermedio (Python/FastAPI) que recibe los mensajes de WhatsApp y se los pasa al Agente SQL.
- `evolution_postgres` y `evolution_redis`: Bases de datos internas para Evolution API.

## 2. Puesta en Marcha

1.  Levanta los servicios:

    ```bash
    docker compose up -d
    ```

2.  Verifica que Evolution API esté corriendo:
    - Entra a `http://localhost:8080` (O la IP de tu servidor).
    - Deberías ver un mensaje JSON o la documentación si está habilitada.

## 3. Conectar tu número (QR Code)

Necesitamos crear una "instancia" y escanear el QR.

### Paso A: Crear Instancia

Ejecuta este comando (puedes usar Postman o curl):

```bash
curl --request POST \
  --url http://localhost:8080/instance/create \
  --header 'apikey: 429683C4C977415CAAFCCE10F7D57E11' \
  --header 'Content-Type: application/json' \
  --data '{
    "instanceName": "sql_agent",
    "token": "random_secure_token",
    "qrcode": true
}'
```

Debería devolverte un JSON con `"status": "CREATED"`.

### Paso B: Escanear QR

Una vez creada, pide el QR:

```bash
curl --request GET \
  --url http://localhost:8080/instance/connect/sql_agent \
  --header 'apikey: 429683C4C977415CAAFCCE10F7D57E11'
```

Te devolverá una imagen en base64 o una URL para ver el QR. Escanéalo con tu celular (WhatsApp -> Dispositivos Vinculados).

## 4. Configurar el Webhook

Una vez conectado, dile a Evolution API que envíe los mensajes a nuestro bridge `whatsapp_bridge` **incluyendo el secreto**:

> ⚠️ **IMPORTANTE:** Reemplaza `secret_agent_key` con el valor real que definiste en tu `.env`.

```bash
curl --request POST \
  --url http://localhost:8080/webhook/set/sql_agent \
  --header 'apikey: 429683C4C977415CAAFCCE10F7D57E11' \
  --header 'Content-Type: application/json' \
  --data '{
    "enabled": true,
    "url": "http://whatsapp_bridge:8001/webhook?secret=secret_agent_key",
    "webhookByEvents": true,
    "events": [
        "MESSAGES_UPSERT"
    ]
}'
```

**¡Listo!**
Ahora tu webhook está protegido. Si alguien intenta enviar datos falsos sin el `?secret=...`, será rechazado.

## 5. Troubleshooting

Si el agente no responde:

1.  Revisa los logs del puente: `docker compose logs -f whatsapp_bridge`
2.  Revisa los logs de Evolution: `docker compose logs -f evolution_api`
