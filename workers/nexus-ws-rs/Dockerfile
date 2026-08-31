FROM rust:1.79-slim@sha256:073c8e7ae12d2637d1d541cb0f3f9d92bfa22c97e2e45db87a9fc6a90c9a7f22 AS builder
WORKDIR /app
COPY Cargo.toml ./
COPY src ./src
RUN cargo build --release

FROM debian:bookworm-slim@sha256:abd67ffcfa541b485a3dff59865ab629aa048a6c613e639d36e7456b0b229241 AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates wget && rm -rf /var/lib/apt/lists/*
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker
WORKDIR /app
COPY --from=builder /app/target/release/nexus-ws ./
USER worker

EXPOSE 8004
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost:8004/health || exit 1

CMD ["./nexus-ws"]
