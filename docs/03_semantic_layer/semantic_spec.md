# Especificación de la Capa Semántica e Hidratación de Datos

## 1. Introducción
La Capa Semántica es el componente crítico que transforma el esquema técnico "crudo" de la base de datos (tablas, columnas, tipos de datos) en un **Contexto de Negocio** comprensible para el Agente de IA.

Sin esta capa, el Agente intentará adivinar relaciones basándose solo en nombres de columnas (a menudo crípticos), lo que deriva en una baja precisión de ejecución.

## 2. Objetivos Arquitectónicos
1. **Abstracción:** Desacoplar el Agente de la estructura física de la DB.
2. **Enriquecimiento:** Añadir descripciones de negocio, sinónimos y métricas calculadas que no existen en el SQL.
3. **Resiliencia al Cambio (Schema Drift):** Permitir que la documentación se actualice automáticamente cuando la base de datos cambie.
4. **Resolución de Entidades:** Capacidad de mapear términos vagos del usuario ("ventas de apple") a valores exactos en la base de datos ("Apple Computer, Inc.").

## 3. El Artefacto Central: `dictionary.yaml`
La "Fuente de Verdad" del sistema será un archivo YAML estructurado. Este archivo no se escribe 100% a mano; es generado inicialmente por scripts y refinado por humanos.

### Estructura del Esquema
```yaml
tables:
  - name: t_orders  # Nombre real en DB
    friendly_name: "Pedidos"
    description: "Tabla transaccional que registra todas las compras finalizadas."
    columns:
      - name: net_amt
        description: "Monto total de la venta excluyendo impuestos."
        synonyms: ["ingresos", "venta neta", "plata"]
      - name: status_id
        description: "Estado del pedido (1=Pendiente, 2=Pagado, 3=Cancelado)."
        # Metadata crítica para que el LLM sepa qué filtrar
        valid_values: 
          - "1: Pendiente"
          - "2: Pagado"
          - "3: Cancelado"
    
    # Ejemplos Few-Shot específicos para esta tabla
    examples:
      - question: "¿Cuántos pedidos se cancelaron ayer?"
        sql: "SELECT count(*) FROM t_orders WHERE status_id = 3 AND created_at >= CURDATE() - INTERVAL 1 DAY"
```

## 4. Flujo de Hidratación Automática (Pipeline)
Para evitar mantener documentación obsoleta, implementamos un pipeline de hidratación.

```mermaid
graph TD
    DB[(MySQL Producción)] -->|SQLAlchemy Inspector| Extractor[Script Extractor]
    Extractor -->|Esquema Crudo (JSON)| Annotator[🤖 Agente Annotador (LLM)]
    
    Annotator -->|Prompt: 'Describe estas columnas'| LLM((OpenAI/Anthropic))
    LLM -->|Descripciones + Sinónimos| Annotator
    
    Annotator -->|Genera/Actualiza| YAML[dictionary.yaml]
    
    Human[👤 Desarrollador] -->|Revisión/Ajuste Manual| YAML
```

### Componentes del Pipeline
- **Extractor (schema.py):** Lee metadatos técnicos (FKs, tipos).
- **Annotador (hydrator.py):** Usa un LLM barato (ej. GPT-4o-mini) para generar descripciones iniciales de tablas desconocidas.
- **Persistencia (manager.py):** Guarda el YAML respetando las ediciones manuales previas (no sobrescribe trabajo humano si ya existe).

## 5. Estrategia de Búsqueda de Valores (Fuzzy Search)
Uno de los fallos más comunes en Text-to-SQL es la alucinación de valores literales (ej: buscar `WHERE client = 'CocaCola'` cuando en la DB es `'Coca-Cola FEMSA'`).

### Solución: Interceptor de Valores
1. **Detección:** El Agente identifica que la pregunta filtra por una entidad nombrada (Cliente, Producto, Ciudad).
2. **Búsqueda:** Se utiliza la librería `thefuzz` (Levenshtein Distance) o búsqueda vectorial (ChromaDB) contra una lista de valores únicos extraídos de la columna relevante.
3. **Inyección:** Se inyecta el valor real encontrado en el prompt del sistema.

**Nota:** Para tablas masivas (>1M filas), no se indexan todos los valores. Se utiliza una estrategia de "Top N valores frecuentes" o un índice vectorial externo.
