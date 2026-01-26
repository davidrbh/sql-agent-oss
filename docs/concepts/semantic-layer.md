# Especificación de la Capa Semántica y Seguridad (v4.0)

## 1. Introducción

La **Capa Semántica** es el puente entre el lenguaje natural del usuario y el esquema físico de la base de datos. En la versión 4.0, esta capa no solo define "qué significan los datos", sino que trabaja en conjunto con el nuevo **SQLGuard** para garantizar que el acceso a esos datos sea seguro.

El archivo `config/business_context.yaml` sigue siendo la fuente de verdad del negocio.

## 2. SQLGuard: El Firewall Cognitivo

Antes de que cualquier consulta generada por el LLM llegue a la base de datos, debe pasar por el **SQLGuard**. Este componente utiliza el contexto semántico para validar la intención.

### 2.1. Validación AST (Abstract Syntax Tree)
El guardián no usa expresiones regulares. Descompone la consulta SQL en un árbol matemático y verifica:
1.  **Nodo Raíz:** Debe ser estrictamente `SELECT`.
2.  **Prohibiciones:** Bloquea nodos `DELETE`, `DROP`, `UPDATE`, `ALTER`, `TRUNCATE`.
3.  **Transpilación:** Reescribe la consulta para eliminar comentarios maliciosos (`--`) o intentos de ofuscación.

### 2.2. Reglas de Negocio en el Prompt
El `business_context.yaml` inyecta reglas de seguridad "blandas" en el prompt del sistema:
-   "Nunca hagas `SELECT *` en la tabla `users`".
-   "Usa siempre `LIMIT` si no hay filtros de fecha".

El `SQLGuard` actúa como la red de seguridad "dura" si el LLM ignora estas instrucciones blandas.

## 3. Estructura del `business_context.yaml`

(Sin cambios estructurales mayores en v4.0, pero con mayor énfasis en la definición precisa de entidades para evitar alucinaciones).

### `entities` y `synonyms`
Define los conceptos clave.
```yaml
entities:
  - name: user
    synonyms: ["cliente", "deudor", "usuario"] # Vital para el Router de Intención
```

### `models`
Mapea tablas físicas a lógicas.
```yaml
models:
  - name: users
    source: "production_db.users" # Nombre real
    security_level: high # (Futuro: usado por SQLGuard para aplicar máscaras)
```

## 4. Flujo de Validación Semántica

1.  **Usuario:** "¿Bórrame el usuario Juan?"
2.  **LLM (Intento):** Genera `DELETE FROM users WHERE name='Juan'`.
3.  **SQLGuard:**
    -   Parsea el SQL -> AST.
    -   Detecta nodo `exp.Delete`.
    -   **BLOQUEA** la ejecución.
    -   Devuelve error al LLM: "⛔ SEGURIDAD: Operación DELETE prohibida".
4.  **Agente:** Responde al usuario: "Lo siento, no tengo permisos para borrar datos, solo para consultarlos".

Esta interacción demuestra cómo la capa semántica y la capa de seguridad trabajan juntas para proteger los datos.
