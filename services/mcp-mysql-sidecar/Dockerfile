# ETAPA 1: Construcción (TypeScript -> JavaScript con SWC)
FROM node:20-alpine AS builder

# Habilitar pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app
COPY package.json pnpm-lock.yaml* ./
COPY .swcrc ./
COPY tsconfig.json ./

# Instalar todas las dependencias
RUN pnpm install

COPY src ./src

# Compilar usando SWC (configurado en package.json)
RUN pnpm run build

# Verificar explícitamente el archivo de salida
RUN ls -R dist

# ETAPA 2: Ejecución
FROM node:20-alpine

FROM node:20-alpine

# Habilitar pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app
COPY package.json pnpm-lock.yaml* ./

# Instalar solo dependencias de producción
RUN pnpm install --prod

# Copia crítica: del builder al runtime
COPY --from=builder /app/dist ./dist

ENV PORT=3002
EXPOSE 3002

CMD ["node", "dist/src/index.js"]
