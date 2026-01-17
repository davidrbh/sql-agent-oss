# Guía de la Capa Semántica (`business_context.yaml`)

## 1. Introducción

La **Capa Semántica** es el verdadero cerebro de negocio de SQL Agent. Este componente, definido en el archivo `config/business_context.yaml`, es lo que eleva al agente de un simple traductor de "texto a SQL" a un verdadero analista que comprende el contexto, las relaciones y la lógica de tu empresa.

**Este es el archivo más importante que debes editar** para enseñarle al agente sobre tus datos.

## 2. Filosofía: Modelos Lógicos vs. Esquema Físico

Un esquema de base de datos (`CREATE TABLE...`) describe la realidad *física* de tus datos. La capa semántica describe la realidad *lógica* de tu negocio.

-   **Realidad Física:** Una tabla `users` tiene columnas como `id`, `fname`, `created_dt`.
-   **Realidad Lógica:** Un `Cliente` (o "usuario", "comprador") tiene un `Nombre` y una `Fecha de Registro`.

El `business_context.yaml` actúa como el puente entre estos dos mundos.

## 3. Estructura del Archivo

El archivo `business_context.yaml` se organiza en las siguientes secciones principales:

-   `meta`: Metadatos globales sobre el proyecto.
-   `entities`: Los "sustantivos" o conceptos clave de tu negocio.
-   `models`: El mapeo de tus tablas de base de datos a los conceptos de negocio.
-   `relationships`: Las reglas para unir (`JOIN`) las tablas entre sí.
-   `metrics`: Indicadores de rendimiento (KPIs) pre-calculados.
-   `business_rules`: Reglas de alto nivel que el agente siempre debe seguir.
-   `usage_examples`: Ejemplos de preguntas y el SQL esperado para guiar al LLM.

---

## 4. Desglose Detallado de Secciones

### `meta`

Define información global que el agente puede usar para formatear respuestas.

```yaml
meta:
  currency_format: "USD"
  time_zone: "America/Caracas"
```

### `entities`

Define los conceptos fundamentales de tu negocio y cómo los usuarios podrían referirse a ellos.

-   `name`: El nombre canónico de la entidad (en singular, minúsculas).
-   `type`: Siempre `primary`.
-   `primary_key`: La clave primaria de la entidad (generalmente un `uuid`).
-   `synonyms`: Una lista de palabras que los usuarios podrían usar para referirse a esta entidad. **Esta es una sección crítica para la comprensión del lenguaje natural.**

```yaml
entities:
  - name: user
    type: primary
    primary_key: uuid
    synonyms: ["cliente", "comprador", "deudor", "usuario"]
```

### `models`

Esta es la sección más extensa. Cada `model` representa una tabla física de tu base de datos y la describe en términos de negocio.

-   `name`: Nombre de la tabla física (ej. `users`).
-   `source`: El nombre completo de la tabla en la base de datos (`database.table_name`).
-   `entities`: A qué entidad de negocio principal se asocia esta tabla.
-   `dimensions`: Columnas descriptivas o categóricas.
    -   `name`: Nombre que el agente usará.
    -   `type`: `string`, `categorical`, `time`, etc.
    -   `col`: Nombre real de la columna en la tabla.
-   `measures`: Columnas numéricas o agregables.
    -   `name`: Nombre que el agente usará.
    -   `type`: `sum`, `avg`, `custom` (para valores directos).
    -   `col`: Nombre real de la columna.
    -   `sql`: Permite definir una medida como una expresión SQL calculada.

```yaml
models:
  - name: users
    source: "bnplsite_credivibes.users"
    entities:
      - name: user
        type: primary
        col: uuid
    dimensions:
      - name: email
        type: string
        col: email
    measures:
      - name: current_debt
        type: custom
        col: balance
```

### `relationships`

Enseña al agente cómo generar `JOIN`s correctos. Sin esto, el agente no puede responder preguntas que involucren más de una tabla.

-   `from_model`/`to_model`: Las dos tablas que se van a unir.
-   `join_type`: `one_to_one`, `many_to_one`, etc.
-   `on`: La **expresión SQL exacta** para el `JOIN`.

```yaml
relationships:
  - from_model: purchases
    to_model: users
    join_type: many_to_one
    on: "purchases.users_id = users.uuid"
```

### `business_rules` y `usage_examples`

Estas secciones son "texto libre" que se inyecta directamente en el prompt del sistema del LLM para darle un contexto de alto nivel y ejemplos de cómo comportarse.

```yaml
business_rules:
  - name: "Anulación"
    description: "Compras con status=2 (Anulado) deben ser excluidas de reportes de venta y deuda real."

usage_examples:
  - question: "¿Qué pagos móviles llegaron hoy?"
    sql: "SELECT reference, amount / convertion_rate as amount_usd FROM payment_checked WHERE type = 'mobile' AND created_at >= CURDATE()"
```

---

## 5. Guía Práctica: Cómo Añadir una Nueva Tabla

Imaginemos que tenemos una nueva tabla `products` en nuestra base de datos.

`CREATE TABLE products ( uuid VARCHAR(36) PRIMARY KEY, name VARCHAR(255), price DECIMAL(10, 2), stock_quantity INT );`

Y queremos que el agente pueda responder: *"¿cuáles son los 5 productos más caros?"*.

#### Paso 1: Definir la Entidad en `entities`

Primero, le decimos al agente qué es un "producto".

```yaml
entities:
  # ... (otras entidades)
  - name: product
    type: primary
    primary_key: uuid
    synonyms: ["producto", "artículo", "item", "mercancía"]
```

#### Paso 2: Definir el Modelo en `models`

Ahora, mapeamos la tabla `products` a sus dimensiones y medidas.

```yaml
models:
  # ... (otros modelos)
  - name: products
    source: "bnplsite_credivibes.products" # Reemplazar con tu nombre de BBDD
    entities:
      - name: product
        type: primary
        col: uuid
    dimensions:
      - name: name
        type: string
        col: name
    measures:
      - name: price
        type: custom
        col: price
      - name: stock
        type: custom
        col: stock_quantity
```

#### Paso 3: Definir las Relaciones en `relationships` (si aplica)

Si `products` se relaciona con `purchases` a través de una tabla intermedia `purchase_items`, necesitaríamos añadir esa relación. Por ahora, como la pregunta es solo sobre productos, no se necesita un `JOIN`.

#### Paso 4: Añadir Ejemplos en `usage_examples` (Recomendado)

Para ayudar al LLM, podemos darle un ejemplo.

```yaml
usage_examples:
  # ... (otros ejemplos)
  - question: "¿Cuáles son los 5 productos más caros?"
    sql: "SELECT name, price FROM products ORDER BY price DESC LIMIT 5"
```

#### Paso 5: Regenerar el Diccionario

Este es el paso final y **obligatorio**. Cada vez que modificas `business_context.yaml`, debes ejecutar el script que "compila" este conocimiento para el agente.

Desde la raíz del proyecto, si usas Docker:
```bash
docker exec -it <ID_DEL_CONTENEDOR_AGENT_HOST> poetry run python scripts/generate_dictionary.py
```
O si corres localmente:
```bash
poetry run python scripts/generate_dictionary.py
```

¡Y listo! El agente ahora conoce la tabla `products` y puede responder preguntas sobre ella.