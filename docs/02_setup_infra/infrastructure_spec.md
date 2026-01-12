# Especificación de Infraestructura y Conectividad

## 1. Diseño del Entorno (Containerization)

El proyecto utiliza **Docker** para orquestar los servicios, garantizando que el entorno de desarrollo sea idéntico en cualquier máquina (Windows, Mac, Linux).

### Servicios Definidos

1.  **Base de Datos Principal (MySQL 8.0):**
    - **Justificación:** Se utiliza MySQL para replicar el entorno de producción del usuario final.
    - **Configuración:** Puerto expuesto `3306`.
    - **Inyección de Datos:** Se utiliza el directorio `./mysql_dump/` mapeado a `/docker-entrypoint-initdb.d`. Cualquier archivo `.sql` colocado aquí se ejecutará automáticamente al crear el contenedor por primera vez.
2.  **Interfaz de Gestión (Adminer):**
    - Herramienta ligera para inspección visual de datos y depuración de queries sin necesidad de clientes instalados localmente.
3.  **WhatsApp Integration (WAHA + Agent Bridge):**
    - **WAHA:** Motor que conecta a WhatsApp via WebJS o Noweb, manejando sesiones y webhooks.
    - **Agent Bridge:** Servidor FastAPI que recibe mensajes de WhatsApp, maneja memoria de conversaciones y orquesta respuestas del agente. Incluye servicios para WhatsApp via WAHA.

## 2. Estrategia de Conexión de Datos

La aplicación Python no se conecta directamente mediante drivers bloqueantes.

### Patrón de Conexión: Singleton Asíncrono

- **Driver:** `aiomysql` + `SQLAlchemy AsyncEngine`.
- **Gestión de Pool:** Se mantiene un pool de conexiones abiertas (min: 5, max: 20) para evitar la sobrecarga de handshake TCP en cada petición del Agente.
- **Singleton:** Se garantiza que solo exista una instancia del motor de base de datos en toda la vida de la aplicación.

## 3. Seguridad de Credenciales y API

- **Principio:** Ninguna credencial se almacena en el código fuente.
- **Implementación:** Se utiliza `python-dotenv` para leer un archivo `.env` local.
- **Variables Requeridas (Base de Datos):**
  - `DB_HOST`, `DB_PORT`: Ubicación del servicio.
  - `DB_USER`, `DB_PASSWORD`: Credenciales de acceso (Limitadas a lectura en producción).
  - `DB_NAME`: Nombre exacto de la base de datos a consultar.
- **Variables Requeridas (API Externa):**
  - `API_BASE_URL`: URL raíz de la API (ej: `https://api.example.com`).
  - `API_AUTH_HEADER`: Nombre del header de autenticación (ej: `x-api-key`, `Authorization`).
  - `API_AUTH_VALUE`: Valor secreto del token/key.

## 4. Documentación de API (Swagger)

Para que el agente pueda interactuar con la API Externa, se requiere:

1. Una especificación **OpenAPI 3.0+** en formato JSON.
2. El archivo debe ubicarse en `docs/swagger.json`.
3. El sistema cargará automáticamente este archivo al inicio para generar el "Mapa Mental" de endpoints disponibles.

## 5. Modalidad de Desarrollo "Local Nativa"

Para desarrolladores que ya poseen una instancia de MySQL corriendo localmente:

1. No es necesario iniciar el contenedor `mysql_db` vía Docker Compose.
2. Se debe configurar el archivo `.env` apuntando a `DB_HOST=127.0.0.1`.
3. Se recomienda usar MySQL versión 8.0+ para compatibilidad total con las funciones de fecha y JSON que podría generar el agente.
