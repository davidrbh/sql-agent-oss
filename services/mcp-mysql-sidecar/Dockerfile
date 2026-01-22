# ----------------------------------------------------
# Stage 1: Dependencies
# ----------------------------------------------------
FROM node:20-alpine AS deps
WORKDIR /app

# Habilitar pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copiar definiciones (Ruta relativa desde la raíz del monorepo)
COPY services/mcp-mysql-sidecar/package.json services/mcp-mysql-sidecar/pnpm-lock.yaml* ./

# Instalar dependencias de producción
RUN pnpm install --prod --no-frozen-lockfile

# ----------------------------------------------------
# Stage 2: Builder
# ----------------------------------------------------
FROM deps AS builder
WORKDIR /app

# Instalar todas las dependencias (incluyendo dev)
RUN pnpm install --no-frozen-lockfile

# Copiar configuraciones de compilación
COPY services/mcp-mysql-sidecar/tsconfig.json ./
COPY services/mcp-mysql-sidecar/.swcrc ./

# Copiar código fuente
COPY services/mcp-mysql-sidecar/src ./src

# Compilar
RUN pnpm run build

# ----------------------------------------------------
# Stage 3: Runner (Production)
# ----------------------------------------------------
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3002

# Crear usuario seguro
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 mcpuser

# Copiar artefactos
COPY --from=deps --chown=mcpuser:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=mcpuser:nodejs /app/dist ./dist
COPY --from=builder --chown=mcpuser:nodejs /app/package.json ./package.json

USER mcpuser

EXPOSE 3002

CMD ["node", "dist/src/index.js"]