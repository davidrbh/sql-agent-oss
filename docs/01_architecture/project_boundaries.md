# Límites y Alcance del Proyecto

## ✅ Dentro del Alcance (In-Scope)
1.  **Consultas de Lectura (SELECT):** Generación de SQL para responder preguntas analíticas.
2.  **Soporte Multi-Dialecto:** Inicialmente PostgreSQL y MySQL.
3.  **Seguridad Pasiva:** Bloqueo de consultas maliciosas antes de la ejecución.
4.  **Autocorrección:** Capacidad de reintentar si la base de datos devuelve un error de sintaxis.
5.  **Capa Semántica:** Definición de métricas de negocio en configuración YAML.

## ❌ Fuera del Alcance (Out-of-Scope)
1.  **Modificación de Datos:** No se soportarán comandos DML (`INSERT`, `UPDATE`, `DELETE`) ni DDL (`CREATE`, `DROP`).
2.  **Administración de Base de Datos:** El agente no creará usuarios, índices ni gestionará backups.
3.  **Procesamiento de Imágenes/Audio:** Entrada estrictamente de texto.
4.  **Conexión a Bases de Datos NoSQL:** (Por ahora) No soporte para Mongo, Redis, etc.
