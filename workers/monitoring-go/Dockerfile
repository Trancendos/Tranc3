# ── Build stage ─────────────────────────────────────────────────────────────
FROM golang:1.22-alpine AS builder

WORKDIR /src

# Cache dependency downloads separately from source
COPY go.mod go.sum* ./
RUN go mod download

COPY . .

# Produce a fully static binary
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -trimpath -ldflags="-s -w" -o /monitoring-go .

# ── Final stage ──────────────────────────────────────────────────────────────
FROM gcr.io/distroless/static-debian12:nonroot

# Copy binary from builder
COPY --from=builder /monitoring-go /monitoring-go

# distroless:nonroot ships with uid 65532; declare it explicitly for Trivy DS-0002
USER 65532:65532

EXPOSE 8007

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["/monitoring-go", "-healthcheck"]

ENTRYPOINT ["/monitoring-go"]
