FROM node:24-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS builder

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY tsconfig.json ./
COPY src/ ./src/
RUN npm run build

# ---- runtime ----
FROM node:24-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e

RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker package.json package-lock.json* ./
RUN npm ci --omit=dev

COPY --chown=worker:worker --from=builder /app/dist ./dist

USER worker

EXPOSE 8092
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD node -e "require('http').get('http://localhost:8092/health', r => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))" || exit 1

CMD ["node", "dist/server.js"]
