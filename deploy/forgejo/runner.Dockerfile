# deploy/forgejo/runner.Dockerfile
# Custom act-runner image with all Trancendos CI/CD tools pre-installed.
#
# Build:
#   docker build -f deploy/forgejo/runner.Dockerfile -t trancendos/act-runner:latest .
#
# Tools included:
#   - flyctl (Fly.io deploy)
#   - wrangler (Cloudflare Workers deploy)
#   - Node.js 20 (LTS)
#   - Python 3.11
#   - pip security tools: pip-audit, bandit, safety, semgrep
#   - gitleaks v8
#   - git, curl, jq, make

FROM code.forgejo.org/forgejo/runner:3

USER root

# ── System packages ───────────────────────────────────────────────────────────
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    curl wget git jq make ca-certificates gnupg \
    python3.11 python3.11-venv python3-pip \
    && rm -rf /var/lib/apt/lists/*

# ── Node.js 20 (via NodeSource) ───────────────────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && node --version && npm --version

# ── Wrangler (Cloudflare Workers CLI) ─────────────────────────────────────────
RUN npm install -g wrangler@latest && wrangler --version

# ── flyctl (Fly.io CLI) ───────────────────────────────────────────────────────
RUN curl -L https://fly.io/install.sh | FLYCTL_INSTALL=/usr/local sh \
    && flyctl version

# ── Python security tools ─────────────────────────────────────────────────────
RUN python3 -m pip install --no-cache-dir --upgrade pip \
    && python3 -m pip install --no-cache-dir \
        pip-audit==2.9.0 \
        bandit==1.8.3 \
        semgrep==1.100.0 \
        ruff==0.4.4 \
        mypy==1.10.0

# ── gitleaks ──────────────────────────────────────────────────────────────────
ARG GITLEAKS_VERSION=8.18.4
RUN curl -sSfL \
    "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
    | tar -xz -C /usr/local/bin gitleaks \
    && gitleaks version

# ── Smoke test — all tools present ───────────────────────────────────────────
RUN flyctl version \
    && wrangler --version \
    && python3 --version \
    && node --version \
    && gitleaks version \
    && bandit --version \
    && ruff --version

USER runner
