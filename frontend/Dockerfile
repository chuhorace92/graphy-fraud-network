# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# Static files behind nginx (TRD 11). Runs as non-root on port 8080.
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
ENV API_UPSTREAM=http://api:8000 \
    NGINX_RESOLVER=127.0.0.11
# Only substitute our variables; nginx's own $vars must survive envsubst.
ENV NGINX_ENVSUBST_FILTER="^(API_UPSTREAM|NGINX_RESOLVER)$"
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
