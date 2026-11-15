# COSMIC TRAIL frontend: build the React/Vite/Cesium app, then serve it with nginx.
# nginx also forwards /api/* to the backend container, so the browser talks to a
# single address (http://localhost:8080) and no CORS or localhost/IPv6 issues arise.

# ---- build ---------------------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Empty = same-origin requests (/api/...), proxied by nginx below.
# Set it at build time to point the app at a different backend:
#   docker compose build --build-arg VITE_API_BASE=https://example.org frontend
ARG VITE_API_BASE=""
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build

# ---- serve ---------------------------------------------------------------
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
