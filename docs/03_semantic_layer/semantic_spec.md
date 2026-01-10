# Especificación de la Capa Semántica e Hidratación de Datos V2.5

## 1. Introducción

La Capa Semántica V2.5 evoluciona el concepto de "diccionario simple" a **"Modelos Lógicos de Negocio"**. En lugar de documentar tablas aisladas, definimos entidades de negocio que el agente debe entender, combinando la realidad técnica (esquema DB) con la realidad de negocio (reglas YAML).

## 2. Fuente de Verdad Híbrida

El sistema de hidratación (`hydrator.py`) fusiona dos fuentes primarias:

1.  **Esquema Físico (Automático):** Nombres de tablas, columnas, tipos de datos y claves foráneas extraídas mediante `SQLAlchemy Inspector`.
2.  **Contexto de Negocio (Manual):** Reglas definidas por el humano en `config/business_context.yaml`.

## 3. El Nuevo Artefacto: `business_context.yaml`

A diferencia de versiones anteriores, ahora nos centramos en **Modelos**.

```yaml
# config/business_context.yaml

business_context: "Empresa de logística internacional."

models:
  - name: "Pedidos"
    tables: ["t_orders", "t_order_details"] # Tablas físicas que componen este modelo logic
    description: "Registro central de transacciones de venta."
    columns:
      - name: "t_orders.net_amt"
        description: "Ingreso neto reportable."
        synonyms: ["venta neta", "revenue"]

    filters:
      - name: "Solo Validos"
        sql_fragment: "status_id != 3" # Regla de negocio inyectable
```

## 4. Pipeline de Hidratación Actualizado

El script `scripts/generate_dictionary.py` ejecuta el siguiente flujo:

1.  **Carga:** Lee `config/business_context.yaml`.
2.  **Introspección:** Conecta a la BD y verifica que las tablas mencionadas en el YAML existan.
3.  **Enriquecimiento:**
    - Si una tabla del modelo no tiene descripción, usa un LLM para generarla basada en sus columnas.
    - Toma muestras de datos (3 filas) para entender el formato real.
4.  **Generación:** Escribe el archivo final `data/dictionary.yaml` que consume el agente en tiempo de ejecución.

## 5. Beneficios de la V2.5

- **Agnóstico al Esquema:** Si cambias el nombre físico de una columna, solo actualizas el mapeo en el YAML, el agente sigue entendiendo "Ingresos".
- **Validación de Versión:** El hidratador detecta si estás usando formatos obsoletos y te alerta.
- **Muestreo Real:** Inyecta ejemplos reales de datos en el prompt para evitar alucinaciones de formato (ej: fechas `YYYY-MM-DD` vs `DD/MM/YYYY`).

## 6. Búsqueda de Valores (Fuzzy Search)

_Se mantiene la funcionalidad de intercepción de entidades utilizando `thefuzz` y bases de datos vectoriales para mapear términos vagos a valores exactos de base de datos._
