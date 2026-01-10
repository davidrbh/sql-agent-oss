# Límites y Alcance del Proyecto

## ✅ Dentro del Alcance (In-Scope)

1.  **Consultas de Lectura (SELECT):** Generación de SQL para responder preguntas analíticas.
2.  **Consumo de APIs (GET):** Recuperación de información en tiempo real mediante endpoints HTTP seguros ("Read-Only").
3.  **Soporte Multi-Dialecto:** Inicialmente PostgreSQL y MySQL.
4.  **Seguridad Pasiva:** Bloqueo de consultas SQL maliciosas y restricción de métodos HTTP "Write" (POST/PUT/DELETE) por defecto.
5.  **Autocorrección (Self-Healing):** Capacidad de reintentar generación SQL ante errores de sintaxis y manejo de errores de conexión API.
6.  **Capa Semántica:** Definición de métricas de negocio en configuración YAML.

## ❌ Fuera del Alcance (Out-of-Scope)

1.  **Modificación de Datos:** No se soportarán comandos DML (`INSERT`, `UPDATE`, `DELETE`) ni DDL (`CREATE`, `DROP`) vía SQL.
2.  **Operaciones API de Escritura:** (Actualmente) El agente está restringido a métodos seguros (`GET`) para evitar acciones irreversibles en sistemas externos.
3.  **Administración de Base de Datos:** El agente no creará usuarios, índices ni gestionará backups.
4.  **Procesamiento de Imágenes/Audio:** Entrada estrictamente de texto.
5.  **Conexión a Bases de Datos NoSQL:** (Por ahora) No soporte para Mongo, Redis, etc.
