#!/bin/sh
# Runtime environment injection for the production nginx container.
# Called by the Docker CMD before starting nginx — writes /usr/share/nginx/html/env.js
# with values from container env vars, enabling zero-rebuild config changes.
#
# Usage in Dockerfile:
#   COPY scripts/inject-env.sh /docker-entrypoint.d/10-inject-env.sh
#   RUN chmod +x /docker-entrypoint.d/10-inject-env.sh

set -e

ENV_FILE="/usr/share/nginx/html/env.js"

# Escape a value for safe embedding inside a JS double-quoted string.
# Strips characters that could break out of the string context.
js_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/'"'"'/\\'"'"'/g; s/`/\\`/g'
}

cat > "$ENV_FILE" << EOF
// Runtime environment — injected at container start (do not edit manually)
window.__ENV__ = {
  VITE_API_URL: "$(js_escape "${VITE_API_URL:-}")",
  VITE_WS_URL: "$(js_escape "${VITE_WS_URL:-}")",
  VITE_NANO_URL: "$(js_escape "${VITE_NANO_URL:-}")",
  VITE_AUTH_URL: "$(js_escape "${VITE_AUTH_URL:-}")",
  ENVIRONMENT: "$(js_escape "${ENVIRONMENT:-production}")"
};
EOF

echo "env.js written: VITE_API_URL=${VITE_API_URL:-<unset>}"
