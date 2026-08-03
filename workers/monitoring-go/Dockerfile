# ── Build stage ─────────────────────────────────────────────────────────────
FROM golang:1.22-alpine@sha256:1699c10032ca2582ec89a24a1312d986a3f094aed3d5c1147b19880afe40e052 AS builder

WORKDIR /src

# Cache dependency downloads separately from source
COPY go.mod go.sum* ./
RUN go mod download

COPY . .

# Produce a fully static binary
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -trimpath -ldflags="-s -w" -o /monitoring-go .

# ── Final stage ──────────────────────────────────────────────────────────────
FROM gcr.io/distroless/static-debian12:nonroot@sha256:f5b485ea962d9bd1186b2f6b3a061191539b905b82ec395de78cbfae51f20e35

# Copy binary from builder
COPY --from=builder /monitoring-go /monitoring-go

# distroless:nonroot ships with uid 65532; declare it explicitly for Trivy DS-0002
USER 65532:65532

EXPOSE 8007

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["/monitoring-go", "-healthcheck"]

ENTRYPOINT ["/monitoring-go"]
