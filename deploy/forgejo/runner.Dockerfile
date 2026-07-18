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

# Docker 23+ uses BuildKit by default, and a BuildKit `docker build` requires
# the Buildx plugin (the classic builder still exists as a deprecated
# fallback via DOCKER_BUILDKIT=0, but nothing here sets that, and relying on
# a deprecated path isn't the goal). The static CLI tarball above does NOT
# include Buildx. Installed to the system-wide plugin dir (not
# ~/.docker/cli-plugins) so it's found regardless of which user runs it —
# this stage runs as root, but the final image switches to USER runner.
#
# SHA-256 pinned below so a compromised/modified release can't silently enter
# this privileged (deploy-host) image's toolchain. IMPORTANT: this repo's
# build sandbox has no network path to github.com, so the hash below —
# sourced from an automated PR review suggestion, not independently fetched
# from docker/buildx's own checksums.txt — has NOT been verified against the
# upstream release. Before this Dockerfile builds in any real deploy
# pipeline, an operator with real GitHub access MUST download
# https://github.com/docker/buildx/releases/download/v${DOCKER_BUILDX_VERSION}/checksums.txt,
# confirm the linux-amd64 line matches the value below, and only then trust
# this pin — do not treat its mere presence here as proof it was checked. If
# you bump DOCKER_BUILDX_VERSION, get the new hash the same verified way.
ARG DOCKER_BUILDX_VERSION=0.19.2
ARG DOCKER_BUILDX_SHA256=a5ff61c0b6d2c8ee20964a9d6dac7a7a6383c4a4a0ee8d354e983917578306ea
RUN mkdir -p /usr/local/lib/docker/cli-plugins \
    && curl -sSfL \
    "https://github.com/docker/buildx/releases/download/v${DOCKER_BUILDX_VERSION}/buildx-v${DOCKER_BUILDX_VERSION}.linux-amd64" \
    -o /usr/local/lib/docker/cli-plugins/docker-buildx \
    && echo "${DOCKER_BUILDX_SHA256}  /usr/local/lib/docker/cli-plugins/docker-buildx" | sha256sum -c - \
    && chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx \
    && docker buildx version

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
    && docker --version \
    && docker buildx version

USER runner

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
  CMD which act_runner || exit 1
