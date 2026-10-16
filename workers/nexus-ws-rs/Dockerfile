FROM rust:1.98-slim@sha256:4cd829461bd5c4d511c32e269da9cb8929223b666519d8004e35fc8d1d771ab7 AS builder
WORKDIR /app
COPY Cargo.toml ./
COPY src ./src
RUN cargo build --release

FROM debian:bookworm-slim@sha256:88200866dfff7ea7f5cbcb6ec7c8a701889efe6fe859fe64d6990e4b07ea4171 AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates wget && rm -rf /var/lib/apt/lists/*
RUN groupadd -r worker && useradd -r -g worker -d /app -s /sbin/nologin worker
WORKDIR /app
COPY --from=builder /app/target/release/nexus-ws ./
USER worker

EXPOSE 8004
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost:8004/health || exit 1

CMD ["./nexus-ws"]
