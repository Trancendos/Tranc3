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
#   - docker CLI (client only — talks to the /var/run/docker.sock bind-mounted
#     into this container by docker-compose.yml; no dockerd of its own)
#   - git, curl, jq, make

FROM code.forgejo.org/forgejo/runner:3

USER root

# ── System packages ───────────────────────────────────────────────────────────
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    curl wget git jq make ca-certificates gnupg \
    python3.11 python3.11-venv python3-pip \
    && rm -rf /var/lib/apt/lists/*

# ── Docker CLI (client binary only, no dockerd) ───────────────────────────────
# `:host` runner labels execute job steps in this container's own process
# namespace, so a step's `docker build`/`docker push` needs a `docker` binary
# here even though the daemon it talks to (via the mounted socket) is the
# host's. The `docker.io` apt package would also drag in a full second
# dockerd/containerd (~150MB, unused daemon tooling and attack surface on
# an already-privileged image) — Docker's own static CLI tarball ships just
# the client binaries, so extract only `docker` from it, same pattern as
# the gitleaks static binary below.
ARG DOCKER_CLI_VERSION=27.3.1
RUN curl -sSfL \
    "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_CLI_VERSION}.tgz" \
    | tar -xz -C /usr/local/bin --strip-components=1 docker/docker \
    && docker --version

# ── Node.js 20 (via NodeSource) ───────────────────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
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
    && ruff --version \
    && docker --version

USER runner

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
  CMD which act_runner || exit 1
