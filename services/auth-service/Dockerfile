# Build stage
FROM node:20-alpine AS builder

WORKDIR /build

# Install ALL deps (including devDependencies needed for tsc)
COPY package.json package-lock.json* ./
# NPM_REGISTRY can be overridden in GitLab CI to point to Artifactory
ARG NPM_REGISTRY=https://registry.npmjs.org
RUN npm config set registry "$NPM_REGISTRY" && npm ci

COPY tsconfig.json ./
COPY src/ ./src/
RUN npm run build

# Production stage
FROM node:20-alpine AS production

WORKDIR /app

RUN addgroup -S mockingbird && adduser -S mockingbird -G mockingbird

COPY package.json package-lock.json* ./
ARG NPM_REGISTRY=https://registry.npmjs.org
RUN npm config set registry "$NPM_REGISTRY" && npm ci --omit=dev && npm cache clean --force

COPY --from=builder /build/dist ./dist

USER mockingbird

EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD wget -qO- http://localhost:3001/health || exit 1

CMD ["node", "dist/server.js"]
