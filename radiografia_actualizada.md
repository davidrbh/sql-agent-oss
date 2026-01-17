### **Generando radiografía de: /home/davidrbh/Documents/projects/sql-agent-oss**

#### === 1. ESTRUCTURA DEL PROYECTO (TREE) ===
```
. 
├───.dockerignore
├───.env.example
├───.eslintrc.json
├───.gitignore
├───.prettierrc
├───.chainlit/ 
│   ├───config.toml
│   └───translations/ 
│       ├───en-US.json
│       └───... (19 more files)
├───apps/ 
│   └───agent-host/ 
│       ├───Dockerfile
│       ├───poetry.lock
│       ├───pyproject.toml
│       └───src/ 
│           ├───main.py
│           ├───ui.py
│           ├───agent_core/ 
│           │   ├───__init__.py
│           │   ├───graph.py
│           │   ├───api/ 
│           │   ├───config/ 
│           │   ├───core/ 
│           │   │   └───state.py
│           │   ├───llm/ 
│           │   └───utils/ 
│           ├───api/ 
│           │   └───server.py
│           ├───channels/ 
│           │   └───whatsapp/ 
│           │       ├───__init__.py
│           │       └───router.py
│           ├───core/ 
│           ├───features/ 
│           │   └───sql_analysis/ 
│           │       ├───loader.py
│           ├───infra/ 
│           │   └───mcp/ 
│           │       ├───__init__.py
│           │       ├───loader.py
│           │       └───manager.py
│           └───old_sql_agent_trash/ 
├───audit_project.py
├───chainlit.md
├───CHANGELOG.md
├───config/ 
│   ├───business_context.yaml
│   ├───prompts.yaml
│   └───settings.yaml
├───CONTRIBUTING.md
├───data/ 
│   ├───dictionary.yaml
│   └───logs/ 
├───debug_requests.py
├───deploy/ 
│   └───docker/ 
├───docker-compose.yml
├───docs/ 
│   ├───01_architecture/ 
│   ├───02_setup_infra/ 
│   ├───03_semantic_layer/ 
│   ├───04_optimization/ 
│   ├───05_whatsapp_integration.md
│   ├───06_mcp_migration_spec.md
│   └───swagger.json
├───mysql_dump/ 
├───package.json
├───pnpm-lock.yaml
├───pnpm-workspace.yaml
├───README.md
├───reporte_arquitectura.txt
├───scripts/ 
│   ├───generate_dictionary.py
│   ├───list_models.py
│   ├───run_agent.py
│   ├───validator.py
│   └───verify_mcp.py
├───services/ 
│   └───mcp-mysql-sidecar/ 
│       ├───.swcrc
│       ├───Dockerfile
│       ├───package.json
│       ├───pnpm-lock.yaml
│       ├───src/ 
│       │   └───index.ts
│       └───tsconfig.json
├───tsconfig.json
├───turbo.json
└───WARP.md
```

#### === 2. CONTENIDO DE ARCHIVOS CRÍTICOS ===

---
##### FILE: `/home/davidrbh/Documents/projects/sql-agent-oss/docker-compose.yml`
```yaml
services:
  # El Brazo (MySQL Sidecar)
  mcp-mysql:
    build:
      context: ./services/mcp-mysql-sidecar
    env_file:
      - .env
    environment:
      # Mapeo de variables del .env (DB_*) a las esperadas por el Sidecar (MYSQL_*)
      - MYSQL_HOST=${DB_HOST}
      - MYSQL_USER=${DB_USER}
      - MYSQL_PASSWORD=${DB_PASSWORD}
      - MYSQL_DATABASE=${DB_NAME}
      - MYSQL_PORT=3306
    ports:
      - "3000:3000"
    extra_hosts:
      - "host.docker.internal:host-gateway" # Para conectar a BD en localhost

  # El Cerebro (Agent Host)
  agent-host:
    build:
      context: ./apps/agent-host
    ports:
      - "8000:8000"
    # CAMBIO: Usamos uvicorn para correr server.py (Multicanal) en lugar de chainlit directo
    command: uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
    depends_on:
      - mcp-mysql
    env_file:
      - .env
    environment:
      - SIDECAR_URL=http://mcp-mysql:3000
    volumes:
      - ./apps/agent-host/src:/app/src # Hot reload logic support
      - ./config:/app/config
      - ./data:/app/data
      - ./docs:/app/docs # DOCUMENTACIÓN (Swagger.json)

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
      # Eventos que queremos recibir
      - WHATSAPP_WEBHOOK_EVENTS=message
      # Puerto interno
      - PORT=3000
      # Seguridad (Mapeo desde .env)
      - WHATSAPP_API_KEY=${WAHA_API_KEY}
      - WHATSAPP_SWAGGER_USERNAME=${WHATSAPP_SWAGGER_USERNAME}
      - WHATSAPP_SWAGGER_PASSWORD=${WHATSAPP_SWAGGER_PASSWORD}
    volumes:
      - .waha_sessions:/app/sessions # Persistencia de sesión (QR)
    restart: on-failure
```

---
##### FILE: `/home/davidrbh/Documents/projects/sql-agent-oss/config/business_context.yaml`
```yaml
version: "2.5"
project: "credivibes_ai_context"

meta:
  currency_format: "USD"
  time_zone: "America/Caracas"
  description: >
    Capa semántica MAESTRA para la plataforma BNPL Credivibes.

    *** REGLAS DE ORO GLOBALES (MUST READ) ***:

    1. PREFERENCIA POR COLUMNAS TOTALIZADORAS: Si existe 'balance' o 'total', ÚSALA.
       NO calcules sumas manuales (SUM) sobre transacciones a menos que sea un reporte de desglose.
       Confía ciegamente en el dato almacenado en la tabla padre.

    2. MONEDA BASE (USD):
       - Todos los montos financieros (deuda, límites, precios) están almacenados en USD.
       - Montos en VES solo existen en logs bancarios y pagos reportados ('amount_ves').
       - Conversión: siempre usa la tasa almacenada en el registro (amount / rate).

    3. JOINS HÍBRIDOS (UUID vs ID):
       - La regla general es JOIN por UUID (users.uuid = purchases.users_id).
       - EXCEPCIONES IMPORTANTES: 'credit_evaluations' usa ID numérico (users.id) y 'merchant_branches' usa ID numérico de merchant (merchant.id).
       - Verifica siempre la sección 'relationships' antes de generar SQL.

entities:
  # Actores
  - name: user
    type: primary
    primary_key: uuid
    synonyms:
      [
        "cliente",
        "comprador",
        "deudor",
        "solicitante",
        "usuario",
        "persona",
        "persona natural",
        "persona jurídica",
      ]
  - name: merchant
    type: primary
    primary_key: uuid
    synonyms:
      [
        "comercio",
        "tienda",
        "aliado",
        "proveedor",
        "negocio",
        "empresa",
        "negocio",
      ]
  - name: merchant_branch
    type: primary
    primary_key: uuid
    synonyms: ["sucursal", "sede", "filial"]
  - name: merchant_user
    type: primary
    primary_key: uuid
    synonyms:
      [
        "vendedor",
        "cajero",
        "empleado",
        "funcionario",
        "personal",
        "trabajador",
      ]

  # Transacciones
  - name: purchase
    type: primary
    primary_key: uuid
    synonyms:
      [
        "crédito",
        "orden",
        "financiamiento",
        "compra",
        "venta",
        "pago",
        "cobro",
        "factura",
        "factura de venta",
        "factura de crédito",
      ]
  - name: purchase_intent
    type: primary
    primary_key: id
    synonyms: ["intento", "solicitud", "pre-aprobación"]
  - name: purchase_payment
    type: primary
    primary_key: uuid
    synonyms: ["cuota", "letra", "installment", "pago", "cobro"]

  # Dinero & Auditoría
  - name: verified_payment
    type: primary
    primary_key: uuid
    synonyms:
      [
        "pago verificado",
        "pago reportado",
        "auditoría",
        "pago",
        "cobro",
        "factura",
        "factura de venta",
        "factura de crédito",
      ]
  - name: bank_notification
    type: primary
    primary_key: id
    synonyms: ["log bancario", "notificación de banco", "pago crudo", "webhook"]

models:
  # -----------------------------------------------------------------
  # MODULE: USERS & RISK
  # -----------------------------------------------------------------
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
        pii: true
      - name: status
        type: categorical
        col: status
        try_cast_to: integer
        description: "1: Activo, 0: Inactivo"
        allowed_values: ["1", "0"]
      - name: created_at
        type: time
        col: created_at
    measures:
      - name: current_debt
        type: custom
        col: balance
        description: >
          Deuda total pendiente. FUENTE DE VERDAD.
          NOTA: Un valor positivo significa que el usuario DEBE dinero.
          NO intentar calcular esto sumando compras; usa siempre este valor.
      - name: credit_limit
        type: custom
        col: credit_limit

  - name: users_profile
    source: "bnplsite_credivibes.users_profile"
    entities:
      - name: user
        type: foreign
        col: users_id
    dimensions:
      - name: name
        type: string
        col: name
      - name: lastname
        type: string
        col: lastname
      - name: phone
        type: string
        col: phone
        pii: true
      - name: document
        type: string
        col: document
        pii: true

  - name: users_score
    source: "bnplsite_credivibes.users_score"
    entities:
      - name: user
        type: foreign
        col: users_id # Relación por UUID
    dimensions:
      - name: score
        type: number
        col: score
        description: "Puntaje de crédito interno (Score)."

  - name: credit_evaluations
    source: "bnplsite_credivibes.credit_evaluations"
    entities:
      - name: user
        type: foreign
        col: user_id # WARNING: Uses Numeric ID
    dimensions:
      - name: final_credit_limit
        type: number
        col: final_credit_limit
      - name: evaluation_result
        type: string
        col: evaluation_result
    measures:
      - name: limit_granted
        type: max
        col: final_credit_limit

  # -----------------------------------------------------------------
  # MODULE: MERCHANT
  # -----------------------------------------------------------------
  - name: merchant
    source: "bnplsite_credivibes.merchant"
    entities:
      - name: merchant
        type: primary
        col: uuid
    dimensions:
      - name: name
        type: string
        col: name
      - name: trade_name
        type: string
        col: trade_name
      - name: montoMinimo
        type: number
        col: montoMinimo
        description: "Monto mínimo de venta para financiar."
      - name: porcentajesInicial
        type: string
        col: porcentajesInicial
        description: "JSON con % de inicial permitidos."
      - name: cuotasPermitidas
        type: string
        col: cuotasPermitidas
        description: "JSON con plazos permitidos."
    measures:
      - name: monthly_fee
        type: sum
        col: monthly_fee

  - name: merchant_branches
    source: "bnplsite_credivibes.merchant_branches"
    entities:
      - name: merchant_branch
        type: primary
        col: uuid
      - name: merchant
        type: foreign
        col: merchant_id # WARNING: Uses Numeric ID
    dimensions:
      - name: name
        type: string
        col: name
      - name: state
        type: string
        col: estado

  - name: merchant_users
    source: "bnplsite_credivibes.merchant_users"
    entities:
      - name: merchant_user
        type: primary
        col: uuid
      - name: merchant
        type: foreign
        col: merchant_id
    dimensions:
      - name: role
        type: categorical
        col: role
      - name: username
        type: string
        col: nickname

  - name: merchant_user_branches
    source: "bnplsite_credivibes.merchant_user_branches"
    entities:
      - name: merchant_user
        type: foreign
        col: merchant_user_id # ID numérico
      - name: merchant_branch
        type: foreign
        col: branch_id # ID numérico

  # -----------------------------------------------------------------
  # MODULE: PURCHASES (Action)
  # -----------------------------------------------------------------
  - name: purchases
    source: "bnplsite_credivibes.purchase"
    entities:
      - name: purchase
        type: primary
        col: uuid
      - name: user
        type: foreign
        col: users_id
      - name: merchant
        type: foreign
        col: merchant_id
      - name: merchant_branch
        type: foreign
        col: merchant_branches_id
    dimensions:
      - name: status
        type: categorical
        col: status
        try_cast_to: integer
        description: "0: Progreso, 1: Completado, 2: Anulado"
        allowed_values: ["0", "1", "2"]
      - name: transaction_id
        type: string
        col: transaction_id
      - name: created_at
        type: time
        col: created_at
      - name: is_overdue
        type: boolean
        sql: "EXISTS (SELECT 1 FROM purchase_payment pp WHERE pp.purchase_id = purchase.uuid AND pp.type = 'quote' AND pp.status != 1 AND pp.valid_until_time < UNIX_TIMESTAMP(NOW()))"
    measures:
      - name: total_billed
        type: sum
        col: total
        description: "Monto Venta Total (Principal + Intereses + Inicial)."
      - name: financed_amount
        type: sum
        sql: "purchase.total - purchase.initial_fee"
        description: "Monto Financiado (Deuda neta inicial)."

  - name: purchase_intents
    source: "bnplsite_credivibes.purchase_intent"
    entities:
      - name: purchase_intent
        type: primary
        col: id
        col_uuid: uuid
    dimensions:
      - name: status
        type: categorical
        col: status
        try_cast_to: integer
        description: "0: Pendiente, 1: Aprobado, 2: Rechazado"
        allowed_values: ["0", "1", "2"]
      - name: created_at
        type: time
        col: created_at
    measures:
      - name: amount_requested
        type: sum
        col: total

  - name: purchase_payments
    source: "bnplsite_credivibes.purchase_payment"
    entities:
      - name: purchase_payment
        type: primary
        col: uuid
      - name: purchase
        type: foreign
        col: purchase_id
    dimensions:
      - name: type
        type: categorical
        col: type
        allowed_values: ["quote", "initial_fee"]
      - name: status
        type: categorical
        col: status
        try_cast_to: integer
        description: "0: Pendiente, 1: Pagado, 2: Anulado, 5: Parcial"
        allowed_values: ["0", "1", "2", "5"]
      - name: due_date
        type: time
        sql: "FROM_UNIXTIME(valid_until_time)"
    measures:
      - name: amount_due
        type: sum
        col: amount
      - name: amount_paid
        type: sum
        col: amount_payed

  # -----------------------------------------------------------------
  # MODULE: PAYMENTS & BANKING
  # -----------------------------------------------------------------
  - name: verified_payments
    source: "bnplsite_credivibes.payment_checked"
    entities:
      - name: verified_payment
        type: primary
        col: uuid
      - name: purchase
        type: foreign
        col: purchase_id
      - name: user
        type: foreign
        col: users_id
    dimensions:
      - name: method
        type: categorical
        col: type
        allowed_values: ["mobile", "transfer", "c2p", "cash"]
      - name: reference
        type: string
        col: reference
      - name: bank_code
        type: string
        col: bank_code
      - name: created_at
        type: time
        col: created_at
    measures:
      - name: amount_ves
        type: sum
        col: amount
        description: "Monto en Moneda Local (VES)."
      - name: exchange_rate
        type: avg
        col: convertion_rate
      - name: amount_usd
        type: sum
        sql: "payment_checked.amount / payment_checked.convertion_rate"
        description: "Monto calculado en USD."

  - name: bank_notifications
    source: "bnplsite_credivibes.bank_payment_notifications"
    entities:
      - name: bank_notification
        type: primary
        col: id
    dimensions:
      - name: bank_ref
        type: string
        col: originating_bank_reference
        description: "Referencia bancaria (CRUDA)."
      - name: sender_phone
        type: string
        col: payer_phone
      - name: status
        type: string
        col: status
        allowed_values: ["received", "processed"]
      - name: created_at
        type: time
        col: created_at
    measures:
      - name: amount_ves
        type: sum
        col: amount_ves
        description: "Monto reportado por el banco (Siempre VES)."

relationships:
  # Users Relationships
  - from_model: users_profile
    to_model: users
    join_type: one_to_one
    on: "users_profile.users_id = users.uuid"
  - from_model: users_score
    to_model: users
    join_type: one_to_one
    on: "users_score.users_id = users.uuid"
  - from_model: credit_evaluations
    to_model: users
    join_type: many_to_one
    on: "credit_evaluations.user_id = users.id" # Numeric JOIN

  # Purchase Core
  - from_model: purchases
    to_model: users
    join_type: many_to_one
    on: "purchases.users_id = users.uuid"
  - from_model: purchases
    to_model: merchant
    join_type: many_to_one
    on: "purchases.merchant_id = merchant.uuid"
  - from_model: purchases
    to_model: merchant_branches
    join_type: many_to_one
    on: "purchases.merchant_branches_id = merchant_branches.uuid"

  # Purchase Details
  - from_model: purchase_payments
    to_model: purchases
    join_type: many_to_one
    on: "purchase_payments.purchase_id = purchases.uuid"

  # Payments Audit
  - from_model: verified_payments
    to_model: purchases
    join_type: many_to_one
    on: "verified_payments.purchase_id = purchases.uuid"
  - from_model: verified_payments
    to_model: users
    join_type: many_to_one
    on: "verified_payments.users_id = users.uuid"

  # Merchant Internal
  - from_model: merchant_branches
    to_model: merchant
    join_type: many_to_one
    on: "merchant_branches.merchant_id = merchant.id" # Numeric JOIN

metrics:
  - name: average_order_value
    type: ratio
    numerator: purchases.total_billed
    denominator: purchases.count

  - name: delinquency_rate
    description: "Tasa de Morosidad (Pagos vencidos vs Total)."
    type: ratio
    numerator:
      type: count
      model: purchase_payments
      filter: "type = 'quote' AND status != 1 AND valid_until_time < UNIX_TIMESTAMP(NOW())"
    denominator:
      type: count
      model: purchase_payments
      filter: "type = 'quote' AND status != 1"

  - name: intent_approval_rate
    description: "Tasa de Aprobación: % de intentos de compra que resultan exitosos."
    type: ratio
    numerator:
      type: count
      model: purchase_intents
      filter: "status = 1"
    denominator:
      type: count
      model: purchase_intents

  - name: average_financed_amount
    description: "Ticket Promedio Financiado: Promedio de deuda real originada (Excluye inicial)."
    type: ratio
    numerator:
      type: sum
      sql: "total - initial_fee" # Explicit SQL to avoid dependency resolution issues
    denominator: purchases.count

  - name: active_debtors_ratio
    description: "% de Usuarios con Deuda Activa vs Total Usuarios."
    type: ratio
    numerator:
      type: count
      model: users
      filter: "balance > 0"
    denominator:
      type: count
      model: users
      filter: "status = '1'"

  - name: loan_completion_rate
    description: "Tasa de Finalización: % de créditos pagados totalmente."
    type: ratio
    numerator:
      type: count
      model: purchases
      filter: "status = 1"
    denominator:
      type: count
      model: purchases

business_rules:
  - name: "Regla de Fechas Quincenales"
    description: "Vencimientos: Compras días 1-11 -> Vence 15; 12-26 -> Vence FinMes; 27-31 -> Vence 15 Próximo."

  - name: "Conversión de Moneda"
    description: "Para verificar montos en USD de pagos reportados: verified_payments.amount (VES) / verified_payments.convertion_rate."

  - name: "Conciliación Bancaria"
    description: "bank_notifications es el LOG crudo. verified_payments es el pago PROCESADO. Un join entre ellos es posible via referencia, pero no siempre es 1:1."

  - name: "Anulación"
    description: "Compras con status=2 (Anulado) deben ser excluidas de reportes de venta y deuda real."

  - name: "Política de Riesgo Cero (Bloqueo por Mora)"
    description: "Un usuario NO puede solicitar nuevos créditos si tiene CUALQUIER cuota vencida (is_overdue = TRUE) en créditos anteriores. El sistema bloquea automáticamente nuevos intentos."

  - name: "Pagos en Cascada (Waterfall)"
    description: "Distribución automática de dinero: Los pagos cubren primero la deuda más antigua. Si un pago excede el monto de la cuota actual, el excedente ('surplus') se aplica inmediatamente a la siguiente cuota, generando pagos parciales si es necesario."

  - name: "Configuración Financiera por Comercio"
    description: "Las condiciones de crédito (Recargo, % Inicial, Plazos) NO son universales. Cada 'merchant' define sus reglas en 'cuotasPermitidas' y 'porcentajesInicial'. No asumir condiciones estándar para todos."

usage_examples:
  - question: "¿Qué pagos móviles llegaron hoy?"
    sql: "SELECT reference, amount / convertion_rate as amount_usd FROM payment_checked WHERE type = 'mobile' AND created_at >= CURDATE()"

  - question: "¿Cuántos usuarios tengo con Score > 500?"
    sql: "SELECT COUNT(*) FROM users_score WHERE score > 500"

  - question: "¿Cuáles son las cuotas que vencen en los próximos 7 días? (Cobranza)"
    sql: "SELECT u.email, pp.amount, FROM_UNIXTIME(pp.valid_until_time) as due_date FROM purchase_payment pp JOIN purchases p ON pp.purchase_id = p.uuid JOIN users u ON p.users_id = u.uuid WHERE pp.status = 0 AND pp.type = 'quote' AND pp.valid_until_time BETWEEN UNIX_TIMESTAMP(NOW()) AND UNIX_TIMESTAMP(DATE_ADD(NOW(), INTERVAL 7 DAY))"

  - question: "¿Qué comercios tienen más ventas (en USD) este mes?"
    sql: "SELECT m.trade_name, SUM(p.total) as sales FROM purchase p JOIN merchant m ON p.merchant_id = m.uuid WHERE p.status = 1 AND p.created_at >= DATE_FORMAT(NOW(), '%Y-%m-01') GROUP BY m.trade_name ORDER BY sales DESC LIMIT 5"

  - question: "¿Existen pagos en el banco que no hemos registrado en el sistema? (Huérfanos)"
    sql: "SELECT b.originating_bank_reference, b.amount_ves, b.payer_phone FROM bank_payment_notifications b LEFT JOIN payment_checked v ON b.originating_bank_reference = v.reference WHERE v.uuid IS NULL AND b.created_at >= CURDATE()"

  - question: "Calcular la tasa de aprobación de solicitudes de crédito de la última semana."
    sql: "SELECT COUNT(CASE WHEN status = 1 THEN 1 END) * 100.0 / COUNT(*) as approval_rate FROM purchase_intent WHERE created_at >= DATE_SUB(NOW(), INTERVAL 1 WEEK)"
```

---
##### FILE: `/home/davidrbh/Documents/projects/sql-agent-oss/apps/agent-host/src/api/server.py`
```python
import os
from fastapi import FastAPI
from contextlib import asynccontextmanager
from chainlit.utils import mount_chainlit

# --- CANALES (Channels) ---
from channels.whatsapp.router import router as whatsapp_router
from dotenv import load_dotenv

load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic if any
    print("🚀 Server starting...")
    yield
    print("🛑 Server shutting down...")

app = FastAPI(lifespan=lifespan)

# --- 1. Canal WhatsApp (Webhook) ---
app.include_router(whatsapp_router, prefix="/whatsapp")

# --- 2. Health Check ---
@app.get("/health")
async def health_check():
    return {"status": "ok", "architecture": "hybrid-slice"}

# --- 3. Canal UI (Chainlit) ---
# Montamos la UI en la raíz.
# Chainlit tomará el control de "/" y socket.io
# IMPORTANTE: target es relativo al directorio de ejecución (root del repo en docker)
# En docker: WORKDIR /app
# src está en /app/src
# main.py está en /app/src/main.py
mount_chainlit(app=app, target="src/main.py", path="/")
```

---
##### FILE: `/home/davidrbh/Documents/projects/sql-agent-oss/apps/agent-host/src/main.py`
```python
import sys
import os
import chainlit as cl
from langchain_core.messages import HumanMessage

# --- MCP Imports ---
from mcp import ClientSession
from mcp.client.sse import sse_client
from infra.mcp.manager import MCPSessionManager

# --- FEATURE Imports (Arquitectura Híbrida) ---
# Cargamos la "feature" de Análisis SQL específicamente.
from features.sql_analysis.loader import get_sql_tools, get_sql_system_prompt

# --- CONFIGURACIÓN DE PATH ---
# Aseguramos que el sistema pueda encontrar el paquete 'src'
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, 'src'))

# Importamos el cerebro del agente
from agent_core.graph import build_graph

# URL interna de Docker
SIDECAR_URL = os.getenv("SIDECAR_URL", "http://mcp-mysql:3000")

# --- EVENTOS DE CHAINLIT ---

@cl.on_chat_start
async def on_chat_start():
    """
    Se ejecuta cuando un nuevo usuario inicia una sesión.
    Aquí inicializamos la conexión MCP, cargamos herramientas y construimos el grafo.
    """
    
    # 1. Feedback inicial
    msg = cl.Message(content="🔌 Conectando con el Sidecar MySQL (MCP Protocol)...")
    await msg.send()

    try:
        # 2. Inicializar Conexión MCP Persistente (Auto-Reconnect)
        # Usamos MCPSessionManager para manejar reconexiones automáticas si el socket se cierra.
        mcp_manager = MCPSessionManager(SIDECAR_URL)
        await mcp_manager.connect()
        
        cl.user_session.set("mcp_manager", mcp_manager)
        
        msg.content = "✅ Conexión MCP Establecida. Cargando herramientas..."
        await msg.update()

        # 3. Cargar Herramientas y Contexto (Feature SQL)
        # Usamos el loader específico de la feature SQL
        tools = await get_sql_tools(mcp_manager)
        system_prompt = get_sql_system_prompt()
        
        tool_names = [t.name for t in tools]
        msg.content = f"🔧 Herramientas cargadas: {tool_names}. Construyendo Cerebro..."
        await msg.update()

        # 4. Construir Grafo
        # Ahora inyectamos explícitamente el prompt y las herramientas
        graph = build_graph(tools, system_prompt)
        cl.user_session.set("graph", graph)
        cl.user_session.set("history", [])

        # 5. Bienvenida Final
        msg.content = "👋 **¡Hola! Soy SQL Agent v2.1**
        
Estoy conectado a tu entorno híbrido (Base de Datos + APIs).
Puedo ayudarte a:
* 📊 Consultar datos históricos SQL.
* 🔌 Verificar estados en tiempo real vía API.
* 🔄 Corregir mis propios errores si algo falla.

_¿Qué necesitas saber hoy?_"
        await msg.update()

    except Exception as e:
        msg.content = f"❌ **Error Fatal:** No se pudo conectar al Sidecar.\n\nError: {e}"
        await msg.update()

@cl.on_chat_end
async def on_chat_end():
    """Limpieza de recursos al cerrar la pestaña"""
    # 1. Cerrar Cliente MCP
    manager = cl.user_session.get("mcp_manager")
    if manager:
        await manager.close()
        try:
            await client.__aexit__(None, None, None)
        except Exception as e:
            print(f"Error cerrando Cliente MCP: {e}")

    # 2. Cerrar Transporte SSE
    sse_ctx = cl.user_session.get("sse_ctx")
    if sse_ctx:
        print("🛑 Cerrando conexión MCP...")
        try:
            await sse_ctx.__aexit__(None, None, None)
        except Exception as e:
            print(f"Error cerrando SSE: {e}")

@cl.on_message
async def on_message(message: cl.Message):
    """
    Manejador principal de mensajes.
    Recibe el input del usuario e invoca al agente.
    """
    # Recuperar estado
    graph = cl.user_session.get("graph")
    history = cl.user_session.get("history")
    
    # Placeholder de carga
    msg = cl.Message(content="")
    await msg.send()
    
    try:
        # Añadir mensaje de usuario al historial local (LangGraph espera esto)
        history.append(HumanMessage(content=message.content))
        
        inputs = {
            "messages": history
        }
        
        # Feedback visual
        msg.content = "🔄 _Analizando intención y ejecutando herramientas..._"
        await msg.update()
        
        # Ejecución del Grafo (Async)
        config = {"recursion_limit": 150} # Límite de seguridad aumentado
        result = await graph.ainvoke(inputs, config=config)
        
        # Actualizar historial con lo que devolvió el agente (incluye ToolMessages, AIMessages, etc)
        new_history = result["messages"]
        cl.user_session.set("history", new_history)
        
        # Extraer última respuesta del asistente
        # LangGraph devuelve toda la lista, el último debe ser AIMessage
        final_response_content = new_history[-1].content
        
        # Enviar respuesta final
        msg.content = final_response_content
        await msg.update()
        
    except Exception as e:
        error_msg = f"❌ **Error Crítico:**\n\n```\n{str(e)}\n```"
        msg.content = error_msg
        await msg.update()
        print(f"Error en Chainlit handler: {e}")
```

---
##### FILE: `/home/davidrbh/Documents/projects/sql-agent-oss/apps/agent-host/src/agent_core/core/state.py`
```python
from typing import TypedDict, Annotated, List, Dict, Any
import operator
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    """
    Representa la 'Memoria de Trabajo' del Agente durante una conversación.
    LangGraph pasará este objeto entre los nodos.
    """
    
    # Historial de chat: Lista de mensajes (Human, AI, Tool)
    # operator.add significa que cuando un nodo devuelve mensajes, se AGREGAN a la lista
    messages: Annotated[List[BaseMessage], operator.add]
```

---
##### FILE: `/home/davidrbh/Documents/projects/sql-agent-oss/apps/agent-host/src/agent_core/graph.py`
```python
import os
from typing import List
from langchain_openai import ChatOpenAI
from langchain_core.tools import BaseTool
from langchain_core.messages import ToolMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

# Importa tu estado (asegúrate de que coincida con tu archivo actual)
from agent_core.core.state import AgentState 

# --- La lógica del core es GENÉRICA ---
# No sabe nada de SQL, ni de negocio.
# Solo recibe herramientas y prompts.

def build_graph(tools: List[BaseTool], system_prompt: str):
    """
    Construye el Grafo del Agente inyectando las herramientas dinámicas y el prompt.
    """
    # Configurar el LLM con las herramientas reales
    # Habilitar manejo de errores para que el Agente pueda recuperarse de fallos SQL
    for tool in tools:
        tool.handle_tool_error = True

    # Usamos DeepSeek como LLM principal
    llm = ChatOpenAI(
        model="deepseek-chat",
        temperature=0,
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com"
    )
    llm_with_tools = llm.bind_tools(tools)

    # 2. Nodo del Agente (El Cerebro)
    def agent_node(state: AgentState):
        messages = state["messages"]
        
        # Inyectar System Prompt si no existe
        if not isinstance(messages[0], SystemMessage):
            # Usamos el prompt pasado por argumento
            messages = [SystemMessage(content=system_prompt)] + messages
            
        print(f"DEBUG MESSAGES: {messages}") 

        # --- SANITIZATION FOR DEEPSEEK ---
        # DeepSeek API (OpenAI compat) falla si el contenido de ToolMessage es una lista de dicts.
        # LangChain ToolNode a veces devuelve bloques de contenido multimodal. Lo aplanamos a texto.
        sanitized_messages = []
        for m in messages:
            if isinstance(m, ToolMessage) and isinstance(m.content, list):
                # Unir todos los bloques de texto
                text_content = "".join([
                    block.get("text", "") for block in m.content 
                    if isinstance(block, dict) and block.get("type") == "text"
                ])
                # Crear nueva copia con contenido string
                new_m = ToolMessage(
                    content=text_content, 
                    tool_call_id=m.tool_call_id, 
                    name=m.name,
                    artifact=m.artifact
                )
                sanitized_messages.append(new_m)
            else:
                sanitized_messages.append(m)

        response = llm_with_tools.invoke(sanitized_messages)
        return {"messages": [response]}

    # 3. Nodo de Herramientas (El Brazo)
    # ToolNode de LangGraph ejecuta automáticamente la herramienta que el LLM pida
    # handle_tool_errors=True permite que el nodo capture excepciones y devuelva un mensaje de error al LLM
    tool_node = ToolNode(tools, handle_tool_errors=True)

    # 4. Definición del Flujo (Workflow)
    workflow = StateGraph(AgentState)

    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)

    workflow.set_entry_point("agent")

    # Lógica condicional: ¿El LLM quiere usar una herramienta o responder al usuario?
    def should_continue(state):
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "tools"
        return END

    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            END: END
        }
    )

    # El agente vuelve a pensar después de usar una herramienta
    workflow.add_edge("tools", "agent")

    return workflow.compile()
```

---
##### FILE: `/home/davidrbh/Documents/projects/sql-agent-oss/apps/agent-host/src/features/sql_analysis/loader.py`
```python
import os
import yaml
from pathlib import Path
from langchain_core.messages import SystemMessage
from infra.mcp.loader import get_agent_tools as get_mcp_tools # Reusing existing generic MCP loader if possible
# Assuming infra/mcp/loader.py is generic enough. Let's verify that first.

# We need to calculate paths relative to this feature
# apps/agent-host/src/features/sql_analysis/loader.py

# Detección inteligente del entorno (Docker vs Local)
# En Docker, WORKDIR es /app, así que config suele estar en /app/config
DOCKER_CONFIG_PATH = Path("/app/config")

if DOCKER_CONFIG_PATH.exists():
    CONFIG_DIR = DOCKER_CONFIG_PATH
else:
    # Fallback para entorno local (Monorepo)
    # Subimos niveles hasta encontrar la carpeta config en la raíz del proyecto
    # src/features/sql_analysis/loader.py -> ... -> sql-agent-oss/config
    BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
    CONFIG_DIR = BASE_DIR / "config"

SYSTEM_PROMPT_TEMPLATE = """Eres un experto Agente SQL.

⚠️ REGLAS CRÍTICAS DE SEGURIDAD ⚠️
1. PROHIBIDO ejecutar `SELECT *` en la tabla `users`. Contiene columnas de imágenes Base64 (doc_photo, selfie_photo) que rompen la conexión.
2. ANTES de consultar `users`, SIEMPRE ejecuta `DESCRIBE users` para ver las columnas disponibles.
3. Selecciona SIEMPRE columnas específicas (ej. `SELECT id, name, email FROM users...`).
4. Para otras tablas, inspecciona primero el esquema igualmente.

🎨 ESTILO DE RESPUESTA:
- Sé amable y conciso.
- EVITA el uso excesivo de saltos de línea (\n).
- Cuando listes datos simples (como nombres), úsalos separados por comas.
"""

def load_business_context() -> str:
    """Loads business context from YAML"""
    path = CONFIG_DIR / "business_context.yaml"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"⚠️ Alerta: No se encontró {path}")
        return "Sin contexto definido."

def get_sql_system_prompt() -> str:
    """Generates the full system prompt for SQL Analysis"""
    context = load_business_context()
    return f"""{SYSTEM_PROMPT_TEMPLATE}

📘 CONTEXTO DE NEGOCIO Y DICCIONARIO DE DATOS:
A continuación se definen las entidades, sinónimos y reglas de negocio. ÚSALO para entender qué tabla consultar según los términos del usuario.

```yaml
{context}
```
"""

async def get_sql_tools(mcp_manager):
    """Facade to get tools for this specific feature"""
    # In the future, this could filter specific tools from the MCP session if needed
    from agent_core.api.loader import load_api_tools
    
    mcp_tools = await get_mcp_tools(mcp_manager)
    api_tools = load_api_tools() # Reads config from env
    
    return mcp_tools + api_tools
```