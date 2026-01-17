# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

**SQL Agent OSS** is a hybrid AI agent system that converts natural language to SQL queries and integrates with external APIs. It uses a modern microservices architecture with Python (LangGraph/LangChain) for orchestration and Node.js MCP (Model Context Protocol) sidecars for database access.

### Core Architecture

This is a **distributed AI system** with three main components:

1. **Agent Host** (`apps/agent-host/`): Python-based orchestration layer using LangGraph for agentic workflows
2. **MCP MySQL Sidecar** (`services/mcp-mysql-sidecar/`): TypeScript/Node.js service exposing database tools via MCP protocol over SSE (Server-Sent Events)
3. **WAHA Integration** (Docker): WhatsApp HTTP API for conversational interfaces

**Key Architectural Principle**: The agent (Python) never has direct database credentials. All database operations flow through the MCP sidecar, implementing the principle of least privilege.

### Technology Stack

- **Python**: 3.11+ (AsyncIO-native codebase)
- **Package Manager**: Poetry (Python) + pnpm (TypeScript/monorepo root)
- **AI Framework**: LangGraph + LangChain
- **LLM Provider**: DeepSeek (default), Google Gemini, OpenAI-compatible APIs
- **Database**: MySQL (async via MCP protocol)
- **MCP Protocol**: SSE transport (not stdio) for container isolation
- **UI Options**: Chainlit (chat interface), FastAPI (multi-channel API)

## Directory Structure

```
.
├── apps/
│   └── agent-host/          # Python agent application
│       ├── src/
│       │   ├── agent_core/  # Core agent logic (graph, state, tools)
│       │   ├── api/         # FastAPI multi-channel server
│       │   ├── channels/    # Channel adapters (WhatsApp, Chainlit)
│       │   ├── core/        # Shared utilities (LLM, config)
│       │   ├── features/    # Feature modules (SQL analysis)
│       │   ├── infra/       # Infrastructure (MCP client management)
│       │   ├── main.py      # Chainlit entrypoint
│       │   └── ui.py        # Chainlit UI configuration
│       └── pyproject.toml   # Python dependencies
├── services/
│   └── mcp-mysql-sidecar/   # TypeScript MCP server
│       ├── src/             # Bridge implementation
│       └── package.json     # Node.js dependencies
├── config/
│   ├── business_context.yaml  # Semantic layer (business entities, models)
│   └── settings.yaml          # Application configuration
├── data/
│   └── dictionary.yaml      # Generated semantic dictionary
├── docs/
│   ├── swagger.json         # External API definitions
│   ├── 05_whatsapp_integration.md
│   └── 06_mcp_migration_spec.md
└── scripts/
    ├── run_agent.py           # CLI runner
    ├── generate_dictionary.py # Semantic dictionary generator
    └── list_models.py         # List available LLM models
```

## Common Commands

### Initial Setup

```bash
# Install Python dependencies (agent-host)
cd apps/agent-host
poetry install
poetry shell

# Install Node.js dependencies (root + sidecar)
cd /home/davidrbh/Documents/projects/sql-agent-oss
pnpm install

# Configure environment
cp .env.example .env
# Edit .env with your credentials
```

### Development

```bash
# Run full stack (Docker)
docker compose up -d

# View logs
docker compose logs -f agent-host
docker compose logs -f mcp-mysql
docker compose logs -f waha

# Stop services
docker compose down
```

### Python Development (Agent Host)

```bash
# Generate semantic dictionary (REQUIRED before first run)
poetry run python scripts/generate_dictionary.py

# Run CLI agent
poetry run python scripts/run_agent.py

# Run Chainlit UI (single-channel)
cd apps/agent-host
poetry run chainlit run src/main.py -w

# Run multi-channel API server (WhatsApp + HTTP)
cd apps/agent-host
poetry run uvicorn src.api.server:app --reload --host 0.0.0.0 --port 8000
```

### TypeScript Development (MCP Sidecar)

```bash
cd services/mcp-mysql-sidecar

# Build
pnpm build

# Run in production mode
pnpm start

# Run in development mode
pnpm dev
```

### Linting & Formatting

```bash
# Python (using ruff - configured in pyproject.toml)
cd apps/agent-host
poetry run ruff check .
poetry run ruff format .

# TypeScript/JavaScript (root level)
pnpm lint
pnpm format
```

### Testing

```bash
# Currently no automated test suite
# Manual integration testing via:
poetry run python scripts/run_agent.py
poetry run python scripts/verify_mcp.py

# See CONTRIBUTING.md for test scripts when available
```

## Critical Configuration Files

### Environment Variables (.env)

Key variables you MUST configure:

```bash
# LLM Provider (choose one)
GOOGLE_API_KEY=...           # For Gemini models
DEEPSEEK_API_KEY=...         # For DeepSeek (recommended)

# Database (used by MCP sidecar only)
DB_HOST=localhost
DB_PORT=3306
DB_NAME=...
DB_USER=...
DB_PASSWORD=...
DB_DRIVER=aiomysql           # Always use async driver

# WAHA (WhatsApp)
WAHA_BASE_URL=http://waha:3000
WAHA_API_KEY=...

# External APIs (optional)
API_BASE_URL=...
API_AUTH_HEADER=...
API_AUTH_VALUE=...
```

### Semantic Layer (config/business_context.yaml)

This is the **brain** of the system. It defines:

- **Entities**: Business objects (user, merchant, purchase, etc.)
- **Models**: Database table mappings with semantic annotations
- **Relationships**: How tables join (critical: some use UUID, others use numeric ID)
- **Measures**: Calculated metrics
- **Business Rules**: Global rules embedded in YAML comments

**IMPORTANT RULES FROM CONFIG:**

1. **Always prefer totalized columns** (e.g., `balance`) over manual SUM calculations
2. **Currency is USD by default** - VES only exists in payment logs
3. **JOIN strategy varies**: Most use UUID, but `credit_evaluations` uses numeric ID
4. **Always check relationships section** before generating SQL

When modifying business logic, update this file, then regenerate the dictionary:
```bash
poetry run python scripts/generate_dictionary.py
```

## Architecture Patterns

### Agent Graph Flow (LangGraph)

The agent uses a **self-healing SQL** pattern:

1. **Router Node**: Classifies intent (DATABASE, API, or GENERAL)
2. **Agent Node**: LLM decides which tool to call
3. **Tool Node**: Executes MCP tools or API calls
4. **Error Handling**: If SQL fails, error is passed back to LLM for retry

Located in: `apps/agent-host/src/agent_core/graph.py`

Key insight: The graph is **generic** - it receives tools and system prompt at build time, making it feature-agnostic.

### MCP Protocol Integration

The system uses **SSE (Server-Sent Events)** transport, NOT stdio, for container isolation:

```python
# Connection lifecycle managed in infra/mcp/manager.py
from mcp.client.sse import sse_client

async with sse_client(url="http://mcp-mysql:3000") as (read, write):
    async with ClientSession(read, write) as session:
        # Use session to call tools
```

**Why SSE?** Allows independent container restarts. If MySQL sidecar crashes, only that container restarts - the agent stays alive.

### Multi-Channel Architecture

The system supports multiple input channels through adapters:

- **Chainlit** (`main.py`): Web chat UI
- **WhatsApp** (`channels/whatsapp/`): Via WAHA webhook
- **FastAPI** (`api/server.py`): REST API endpoints

All channels feed into the same LangGraph agent core.

### Feature-Based Organization

New capabilities are added as **features** under `apps/agent-host/src/features/`:

- `features/sql_analysis/`: SQL query generation and execution
- Each feature provides: `get_*_tools()` and `get_*_system_prompt()`

This allows the agent to be extended without modifying core graph logic.

## Development Guidelines

### When Working with SQL Generation

- **Never hardcode table/column names** - always reference `business_context.yaml`
- **Test queries manually first** using the MySQL client before adding to semantic layer
- **Respect the JOIN rules** documented in the YAML (UUID vs numeric ID)
- **Update the dictionary** after changing business_context.yaml

### When Adding New MCP Tools

1. Define the tool in the appropriate MCP server (e.g., `mcp-mysql-sidecar`)
2. The agent will **auto-discover** tools via MCP protocol - no manual registration needed
3. Tools are bound to LLM at graph build time in `graph.py`

### When Modifying LangGraph Nodes

- **Keep nodes pure**: They should only transform state, not have side effects
- **Use typed state**: All graph state must conform to `AgentState` schema
- **Handle errors gracefully**: Use `handle_tool_errors=True` on tools
- **Sanitize messages for DeepSeek**: The LLM fails on multimodal ToolMessage content (see `agent_node` in `graph.py`)

### When Working with WhatsApp Integration

- Session management happens in WAHA, not in the agent
- The agent is stateless per-message - LangGraph handles conversation memory
- Filter status updates using the built-in filter in `channels/whatsapp/`
- See `docs/05_whatsapp_integration.md` for detailed setup

### Async/Await Discipline

**This codebase is 100% AsyncIO.** Never block the event loop:

- ✅ Use `await` for all I/O operations
- ✅ Use `async with` for resource management
- ✅ Use `asyncio.gather()` for concurrent operations
- ❌ Never use `time.sleep()` - use `asyncio.sleep()`
- ❌ Never use synchronous database drivers

## Common Pitfalls

### "Module not found" errors

The project uses `poetry` for Python dependencies. Always work within a poetry shell:

```bash
cd apps/agent-host
poetry shell
```

### MCP Connection Failures

If agent can't connect to MCP sidecar:

1. Verify sidecar is running: `docker compose ps`
2. Check sidecar logs: `docker compose logs mcp-mysql`
3. Verify SIDECAR_URL environment variable matches docker-compose service name
4. Test SSE endpoint directly: `curl http://localhost:3000/sse`

### DeepSeek API Errors

DeepSeek (OpenAI-compatible) has stricter requirements:

- **ToolMessage content must be string**, not list of dicts
- See sanitization logic in `agent_core/graph.py` line 48-65
- Temperature should be 0.0 for deterministic SQL generation

### Docker Container Host Networking

To connect from Docker container to host MySQL:

```yaml
# In docker-compose.yml
extra_hosts:
  - "host.docker.internal:host-gateway"

# Then use in .env:
DB_HOST=host.docker.internal
```

### WhatsApp Status Messages Loop

The agent filters `status@broadcast` to avoid replying to WhatsApp stories. If you're getting unwanted replies, verify the filter in `channels/whatsapp/handler.py`.

## Migration to MCP (v3.0 Roadmap)

The project is transitioning to full MCP architecture. See `docs/06_mcp_migration_spec.md` for:

- Current state: Hybrid (Python agent + Node.js MCP sidecar)
- Target state: All data sources as MCP servers
- Security model: Credentials isolated in sidecars
- Deployment: Kubernetes-ready with sidecar pattern

Key decision: **SSE transport** chosen over stdio for production scalability.

## Troubleshooting

### Agent gives incorrect SQL

1. Check `config/business_context.yaml` for correct table/column mappings
2. Verify relationships section for join strategy
3. Regenerate dictionary: `poetry run python scripts/generate_dictionary.py`
4. Check LLM temperature (should be 0.0 for SQL)

### "Connection pool exhausted"

Increase pool size in `.env`:
```bash
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
```

### Chainlit UI not loading

Chainlit requires specific file structure. Ensure:
- `chainlit.md` exists in project root
- `.chainlit/config.toml` is present
- Run from correct directory: `cd apps/agent-host && poetry run chainlit run src/main.py`

### Docker build fails on MCP sidecar

The sidecar uses SWC compiler. If build fails:

```bash
cd services/mcp-mysql-sidecar
pnpm install --force
pnpm build
```

On Alpine Linux, ensure `@swc/core-linux-x64-musl` is installed (already in package.json).

## Additional Resources

- **LangGraph Docs**: https://langchain-ai.github.io/langgraph/
- **MCP Specification**: https://github.com/modelcontextprotocol
- **WAHA Docs**: https://waha.devlike.pro/
- **DeepSeek API**: https://platform.deepseek.com/docs

For questions, check existing issues or create a new one on GitHub.
