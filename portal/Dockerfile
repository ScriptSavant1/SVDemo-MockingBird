# Stage 1 — build React app
ARG NPM_REGISTRY=https://registry.npmjs.org
FROM node:20-alpine AS builder
WORKDIR /app

ARG NPM_REGISTRY
RUN npm config set registry "${NPM_REGISTRY}"

COPY package*.json ./
RUN npm ci --silent

COPY . .
# Inject build-time env vars via VITE_* prefix
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

# Stage 2 — serve with Nginx
FROM nginx:1.27-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
