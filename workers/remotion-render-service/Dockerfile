FROM node:20-bookworm-slim

# Remotion's headless Chromium render path needs these system libs.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    chromium \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker

WORKDIR /app
COPY --chown=worker:worker package.json ./
RUN npm install --omit=dev

COPY --chown=worker:worker server.js ./
COPY --chown=worker:worker remotion/ ./remotion/

RUN mkdir -p /tmp /renders && chown worker:worker /tmp /renders
USER worker

EXPOSE 8093
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD node -e "require('http').get('http://localhost:8093/health', r => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))" || exit 1

CMD ["node", "server.js"]
