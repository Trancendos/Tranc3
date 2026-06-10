# Tranc3 Frontend — multi-stage production image
#
# Stage 1: build  — Node + Vite produces web/dist/
# Stage 2: serve  — nginx:alpine serves the static bundle
#
# Build:  docker build -t tranc3-web ./web
# Run:    docker run -p 3000:8080 tranc3-web

# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install deps separately for layer caching
COPY package.json package-lock.json* ./
RUN npm ci --prefer-offline

# Copy source and build
COPY . .

# Inject build-time env (API URL can be overridden at build time)
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build

# ── Stage 2: serve ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS production

# Remove default nginx content
RUN rm -rf /usr/share/nginx/html/*

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Custom nginx config: SPA routing (all paths → index.html) + security headers
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Security: run nginx as non-root on an unprivileged port (Trivy AVD-DS-0002)
RUN chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx /var/log/nginx \
    && touch /var/run/nginx.pid \
    && chown nginx:nginx /var/run/nginx.pid

USER nginx

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:8080/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
