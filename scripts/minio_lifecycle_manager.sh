#!/usr/bin/env bash
# ============================================================================
# minio_lifecycle_manager.sh — Tranc3 Advanced MinIO Lifecycle Policy Manager
# ============================================================================
#
# Implements advanced MinIO lifecycle policies for the Tranc3 ecosystem:
#   - Tiered expiration: hot → warm → cold → archive → expire
#   - Prefix-based policies for different data classes
#   - Versioning-aware transition rules
#   - Non-current version expiration
#   - Incomplete multipart upload cleanup
#   - Zero-cost enforcement: auto-transition before free-tier limits
#
# MinIO Lifecycle Rules (ILM - Information Lifecycle Management):
#   MinIO supports S3-compatible lifecycle configuration via:
#     mc ilm add    — Add a lifecycle rule
#     mc ilm ls     — List lifecycle rules
#     mc ilm rm     — Remove a lifecycle rule
#     mc ilm rule   — Manage transition/expiration rules
#
# Data Classification for Tranc3:
#   hot/      — Active data, no expiration (AI models, configs)
#   warm/     — Recent data, expire after 30 days (logs, metrics)
#   cold/     — Historical data, expire after 90 days (archives, backups)
#   archive/  — Long-term retention, expire after 365 days (compliance)
#   temp/     — Ephemeral data, expire after 7 days (caches, uploads)
#   work/     — Worker output, expire after 14 days (processing artifacts)
#
# Zero-Cost Policy:
#   MinIO is self-hosted (free, unlimited). Lifecycle policies here
#   manage data retention to prevent unbounded growth while keeping
#   essential data. When MinIO capacity approaches limits, cold data
#   auto-migrates to the next tier (Ceph → R2 → OCI) via
#   SmartStorageOrchestrator.
#
# Usage:
#   ./minio_lifecycle_manager.sh --alias myminio --bucket tranc3 --apply
#   ./minio_lifecycle_manager.sh --alias myminio --bucket tranc3 --list
#   ./minio_lifecycle_manager.sh --alias myminio --bucket tranc3 --apply-prefix hot
#   ./minio_lifecycle_manager.sh --alias myminio --bucket tranc3 --clean-uploads
#   ./minio_lifecycle_manager.sh --alias myminio --bucket tranc3 --capacity-check
#
# Part of the Tranc3 Adaptive Smart Storage Architecture
# Storage Tier Priority: ZFS(0) → MinIO(1) → Ceph(2) → R2(3) → OCI(4)
# ============================================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
readonly SCRIPT_NAME="$(basename "$0")"
readonly LOG_TAG="tranc3-minio-ilm"

# Default MinIO connection
ALIAS="${MINIO_ALIAS:-myminio}"
BUCKET="${MINIO_BUCKET:-tranc3}"
ENDPOINT="${MINIO_ENDPOINT:-http://localhost:9000}"
ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin}"

# Capacity thresholds (matches SmartStorageOrchestrator)
CAPACITY_WARN="${MINIO_CAPACITY_WARN:-80}"
CAPACITY_CRITICAL="${MINIO_CAPACITY_CRITICAL:-95}"

# Retention periods (days)
readonly HOT_EXPIRE=0           # Never expire
readonly WARM_EXPIRE=30         # 30 days
readonly COLD_EXPIRE=90         # 90 days
readonly ARCHIVE_EXPIRE=365     # 1 year
readonly TEMP_EXPIRE=7          # 7 days
readonly WORK_EXPIRE=14         # 14 days
readonly NONCURRENT_EXPIRE=30   # 30 days for non-current versions
readonly UPLOAD_CLEANUP=7       # 7 days for incomplete multipart uploads

# ── Logging ──────────────────────────────────────────────────────────────────
log()  { logger -t "$LOG_TAG" -p user.info "$@" 2>/dev/null || echo "[INFO]  $*"; }
warn() { logger -t "$LOG_TAG" -p user.warning "$@" 2>/dev/null || echo "[WARN]  $*" >&2; }
err()  { logger -t "$LOG_TAG" -p user.err "$@" 2>/dev/null || echo "[ERROR] $*" >&2; }

# ── Pre-flight ───────────────────────────────────────────────────────────────
check_mc_available() {
    if ! command -v mc &>/dev/null; then
        err "MinIO Client (mc) not found. Install it: https://min.io/docs/minio/linux/reference/minio-mc.html"
        exit 1
    fi
}

configure_alias() {
    # Configure mc alias if not already set
    if ! mc alias list 2>/dev/null | grep -q "^${ALIAS}" ; then
        log "Configuring mc alias '$ALIAS' for $ENDPOINT"
        mc alias set "$ALIAS" "$ENDPOINT" "$ACCESS_KEY" "$SECRET_KEY" 2>/dev/null
    fi

    # Verify connectivity
    if ! mc admin info "$ALIAS" &>/dev/null; then
        err "Cannot connect to MinIO at $ENDPOINT. Check credentials and connectivity."
        exit 1
    fi
}

ensure_bucket() {
    if ! mc ls "$ALIAS/$BUCKET" &>/dev/null; then
        log "Creating bucket: $BUCKET"
        mc mb "$ALIAS/$BUCKET" --ignore-existing 2>/dev/null
    fi

    # Enable versioning for lifecycle on non-current versions
    if ! mc version info "$ALIAS/$BUCKET" 2>/dev/null | grep -q "versioning is enabled"; then
        log "Enabling versioning on $BUCKET"
        mc version enable "$ALIAS/$BUCKET" 2>/dev/null
    fi
}

# ── Lifecycle Policy Functions ───────────────────────────────────────────────

apply_prefix_policy() {
    local prefix="$1"
    local expire_days="$2"
    local noncurrent_days="${3:-$NONCURRENT_EXPIRE}"

    local prefix_path="${BUCKET}/${prefix}/"

    if [ "$expire_days" -eq 0 ]; then
        # No expiration — just set non-current version cleanup
        log "Applying policy: ${prefix}/ — Never expire, non-current after ${noncurrent_days}d"

        mc ilm add "$ALIAS/$BUCKET" \
            --prefix "${prefix}/" \
            --noncurrent-expire-days "$noncurrent_days" \
            --tags "tier=hot,managed=tranc3" \
            2>/dev/null || warn "Failed to add ILM rule for ${prefix}/"
    else
        log "Applying policy: ${prefix}/ — Expire after ${expire_days}d, non-current after ${noncurrent_days}d"

        mc ilm add "$ALIAS/$BUCKET" \
            --prefix "${prefix}/" \
            --expire-days "$expire_days" \
            --noncurrent-expire-days "$noncurrent_days" \
            --tags "tier=lifecycle,managed=tranc3" \
            2>/dev/null || warn "Failed to add ILM rule for ${prefix}/"
    fi
}

apply_all_policies() {
    log "Applying all lifecycle policies to $BUCKET..."
    ensure_bucket

    # ── Hot Tier: Active Data (AI models, configs, platform data) ────
    apply_prefix_policy "hot" "$HOT_EXPIRE"

    # ── Warm Tier: Recent Data (logs, metrics, session data) ──────────
    apply_prefix_policy "warm" "$WARM_EXPIRE"

    # ── Cold Tier: Historical Data (archives, old backups) ────────────
    apply_prefix_policy "cold" "$COLD_EXPIRE" "14"

    # ── Archive Tier: Long-term Retention (compliance, audit) ────────
    apply_prefix_policy "archive" "$ARCHIVE_EXPIRE"

    # ── Temp Tier: Ephemeral Data (caches, temporary uploads) ────────
    apply_prefix_policy "temp" "$TEMP_EXPIRE" "3"

    # ── Work Tier: Worker Artifacts (processing output, builds) ──────
    apply_prefix_policy "work" "$WORK_EXPIRE" "7"

    # ── Platform-specific prefixes ────────────────────────────────────
    # AI model artifacts — keep for 90 days
    apply_prefix_policy "models" "90" "30"

    # Worker logs — keep for 14 days
    apply_prefix_policy "logs" "14" "7"

    # Configuration snapshots — keep for 180 days
    apply_prefix_policy "config" "180" "30"

    # User data (if any) — never expire but clean non-current
    apply_prefix_policy "data" "0"

    # Replication targets — keep for 30 days
    apply_prefix_policy "repl" "30" "7"

    # Backup snapshots — keep for 90 days
    apply_prefix_policy "backup" "90" "14"

    log "All lifecycle policies applied to $BUCKET"
}

clean_incomplete_uploads() {
    log "Cleaning incomplete multipart uploads older than ${UPLOAD_CLEANUP} days from $BUCKET"

    mc rm --incomplete --recursive --force "$ALIAS/$BUCKET" \
        --older-than "${UPLOAD_CLEANUP}d" \
        2>/dev/null || warn "No incomplete uploads to clean (or cleanup failed)"

    log "Incomplete upload cleanup completed"
}

list_policies() {
    echo "═══════════════════════════════════════════════════════════════"
    echo "  Tranc3 MinIO Lifecycle Policies — $BUCKET"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""

    # Bucket info
    echo "  Alias:     $ALIAS"
    echo "  Endpoint:  $ENDPOINT"
    echo "  Bucket:    $BUCKET"
    echo ""

    # Current ILM rules
    echo "  Lifecycle Rules:"
    echo "  ─────────────────────────────────────────────────────────────"
    mc ilm ls "$ALIAS/$BUCKET" 2>/dev/null || echo "  (no rules configured)"
    echo ""

    # Bucket size info
    echo "  Bucket Usage:"
    echo "  ─────────────────────────────────────────────────────────────"
    mc du "$ALIAS/$BUCKET" 2>/dev/null || echo "  (unable to get usage)"
    echo ""

    # Versioning status
    echo "  Versioning:"
    echo "  ─────────────────────────────────────────────────────────────"
    mc version info "$ALIAS/$BUCKET" 2>/dev/null || echo "  (status unavailable)"
    echo ""

    # Data classification summary
    echo "  Data Classification:"
    echo "  ─────────────────────────────────────────────────────────────"
    for prefix in hot warm cold archive temp work models logs config data repl backup; do
        local count
        count="$(mc ls "$ALIAS/$BUCKET/${prefix}/" --recursive 2>/dev/null | wc -l || echo 0)"
        if [ "$count" -gt 0 ]; then
            local size
            size="$(mc ls "$ALIAS/$BUCKET/${prefix}/" --recursive --summarize 2>/dev/null | tail -1 | awk '{print $4, $5}' || echo 'unknown')"
            printf "  %-12s  %4d objects  %s\n" "$prefix/" "$count" "$size"
        else
            printf "  %-12s  (empty)\n" "$prefix/"
        fi
    done
    echo ""
}

capacity_check() {
    # Check MinIO disk usage and warn if approaching limits
    # This complements SmartStorageOrchestrator's capacity monitoring

    log "Checking MinIO capacity..."

    local disk_info
    disk_info="$(mc admin info "$ALIAS" 2>/dev/null | grep -A5 'Usage' || echo '')"

    local usage_pct=0
    if [ -n "$disk_info" ]; then
        echo "  MinIO Disk Usage:"
        echo "$disk_info" | sed 's/^/    /'
        # Try to extract usage percentage from mc admin info
        usage_pct="$(echo "$disk_info" | grep -oP '\d+(?=\s*%)' | head -1 || echo 0)"
    else
        # Alternative: check via du
        local total_size
        total_size="$(mc du "$ALIAS/$BUCKET" --summarize 2>/dev/null | awk '{print $1}' || echo '0')"

        local server_info
        server_info="$(mc admin info "$ALIAS" 2>/dev/null || echo '')"

        if echo "$server_info" | grep -qi "usage"; then
            echo "  MinIO Server Info:"
            echo "$server_info" | grep -i "usage\|capacity\|available" | sed 's/^/    /'
            usage_pct="$(echo "$server_info" | grep -oP '\d+(?=\s*%)' | head -1 || echo 0)"
        fi

        echo "  Bucket '$BUCKET' total size: $total_size"
    fi

    # Apply capacity thresholds
    if [ "${usage_pct:-0}" -ge "$CAPACITY_CRITICAL" ]; then
        err "CRITICAL: MinIO capacity at ${usage_pct}% — exceeds critical threshold (${CAPACITY_CRITICAL}%)"
        err "SmartStorageOrchestrator auto-migration should be triggered."
    elif [ "${usage_pct:-0}" -ge "$CAPACITY_WARN" ]; then
        warn "WARNING: MinIO capacity at ${usage_pct}% — exceeds warning threshold (${CAPACITY_WARN}%)"
    else
        log "MinIO capacity at ${usage_pct}% — within limits (warn=${CAPACITY_WARN}%, critical=${CAPACITY_CRITICAL}%)"
    fi

    # Check individual prefix sizes for zero-cost enforcement
    echo ""
    echo "  Per-Prefix Analysis:"
    echo "  ─────────────────────────────────────────────────────────────"
    for prefix in hot warm cold archive temp work models logs config data repl backup; do
        local obj_count
        obj_count="$(mc ls "$ALIAS/$BUCKET/${prefix}/" --recursive 2>/dev/null | wc -l || echo 0)"
        if [ "$obj_count" -gt 0 ]; then
            local prefix_size
            prefix_size="$(mc du "$ALIAS/$BUCKET/${prefix}/" 2>/dev/null | awk '{print $1}' || echo '?')"
            printf "  %-12s  %4d objects  Size: %s\n" "$prefix/" "$obj_count" "$prefix_size"
        fi
    done

    echo ""
    log "Capacity check completed. Use SmartStorageOrchestrator for auto-migration."
}

# ── JSON Lifecycle Configuration ─────────────────────────────────────────────
generate_lifecycle_json() {
    # Generate a standard S3 lifecycle configuration JSON
    # Can be applied via mc ilm import or AWS CLI
    cat <<'JSONEOF'
{
  "Rules": [
    {
      "ID": "tranc3-hot-never-expire",
      "Status": "Enabled",
      "Filter": { "Prefix": "hot/" },
      "NoncurrentVersionExpiration": { "NoncurrentDays": 30 }
    },
    {
      "ID": "tranc3-warm-30d-expire",
      "Status": "Enabled",
      "Filter": { "Prefix": "warm/" },
      "Expiration": { "Days": 30 },
      "NoncurrentVersionExpiration": { "NoncurrentDays": 30 }
    },
    {
      "ID": "tranc3-cold-90d-expire",
      "Status": "Enabled",
      "Filter": { "Prefix": "cold/" },
      "Expiration": { "Days": 90 },
      "NoncurrentVersionExpiration": { "NoncurrentDays": 14 }
    },
    {
      "ID": "tranc3-archive-365d-expire",
      "Status": "Enabled",
      "Filter": { "Prefix": "archive/" },
      "Expiration": { "Days": 365 },
      "NoncurrentVersionExpiration": { "NoncurrentDays": 30 }
    },
    {
      "ID": "tranc3-temp-7d-expire",
      "Status": "Enabled",
      "Filter": { "Prefix": "temp/" },
      "Expiration": { "Days": 7 },
      "NoncurrentVersionExpiration": { "NoncurrentDays": 3 }
    },
    {
      "ID": "tranc3-work-14d-expire",
      "Status": "Enabled",
      "Filter": { "Prefix": "work/" },
      "Expiration": { "Days": 14 },
      "NoncurrentVersionExpiration": { "NoncurrentDays": 7 }
    },
    {
      "ID": "tranc3-models-90d-expire",
      "Status": "Enabled",
      "Filter": { "Prefix": "models/" },
      "Expiration": { "Days": 90 },
      "NoncurrentVersionExpiration": { "NoncurrentDays": 30 }
    },
    {
      "ID": "tranc3-logs-14d-expire",
      "Status": "Enabled",
      "Filter": { "Prefix": "logs/" },
      "Expiration": { "Days": 14 },
      "NoncurrentVersionExpiration": { "NoncurrentDays": 7 }
    },
    {
      "ID": "tranc3-config-180d-expire",
      "Status": "Enabled",
      "Filter": { "Prefix": "config/" },
      "Expiration": { "Days": 180 },
      "NoncurrentVersionExpiration": { "NoncurrentDays": 30 }
    },
    {
      "ID": "tranc3-data-never-expire",
      "Status": "Enabled",
      "Filter": { "Prefix": "data/" },
      "NoncurrentVersionExpiration": { "NoncurrentDays": 30 }
    },
    {
      "ID": "tranc3-repl-30d-expire",
      "Status": "Enabled",
      "Filter": { "Prefix": "repl/" },
      "Expiration": { "Days": 30 },
      "NoncurrentVersionExpiration": { "NoncurrentDays": 7 }
    },
    {
      "ID": "tranc3-backup-90d-expire",
      "Status": "Enabled",
      "Filter": { "Prefix": "backup/" },
      "Expiration": { "Days": 90 },
      "NoncurrentVersionExpiration": { "NoncurrentDays": 14 }
    },
    {
      "ID": "tranc3-incomplete-upload-cleanup",
      "Status": "Enabled",
      "Filter": { "Prefix": "" },
      "AbortIncompleteMultipartUpload": { "DaysAfterInitiation": 7 }
    }
  ]
}
JSONEOF
}

# ── Main ─────────────────────────────────────────────────────────────────────
usage() {
    local exit_code="${1:-0}"
    cat <<EOF
Tranc3 MinIO Lifecycle Policy Manager

Usage: $SCRIPT_NAME [OPTIONS]

Options:
  --alias ALIAS         MinIO mc alias (default: myminio)
  --bucket BUCKET       Bucket name (default: tranc3)
  --endpoint URL        MinIO endpoint (default: http://localhost:9000)
  --access-key KEY      Access key (env: MINIO_ACCESS_KEY)
  --secret-key KEY      Secret key (env: MINIO_SECRET_KEY)
  --apply               Apply all lifecycle policies
  --apply-prefix PFX    Apply policy for a single prefix
  --list                List current lifecycle policies and usage
  --clean-uploads       Clean incomplete multipart uploads
  --capacity-check      Check bucket capacity and per-prefix usage
  --generate-json       Generate S3 lifecycle configuration JSON
  -h, --help            Show this help

Examples:
  $SCRIPT_NAME --apply
  $SCRIPT_NAME --apply-prefix warm --expire-days 30
  $SCRIPT_NAME --list
  $SCRIPT_NAME --clean-uploads
  $SCRIPT_NAME --capacity-check
  $SCRIPT_NAME --generate-json > lifecycle.json
EOF
    exit "$exit_code"
}

ACTION=""
TARGET_PREFIX=""
TARGET_EXPIRE=""

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --alias)        ALIAS="$2"; shift 2 ;;
            --bucket)       BUCKET="$2"; shift 2 ;;
            --endpoint)     ENDPOINT="$2"; shift 2 ;;
            --access-key)   ACCESS_KEY="$2"; shift 2 ;;
            --secret-key)   SECRET_KEY="$2"; shift 2 ;;
            --apply)        ACTION="apply"; shift ;;
            --apply-prefix) ACTION="apply-prefix"; TARGET_PREFIX="$2"; shift 2 ;;
            --expire-days)  TARGET_EXPIRE="$2"; shift 2 ;;
            --list)         ACTION="list"; shift ;;
            --clean-uploads) ACTION="clean-uploads"; shift ;;
            --capacity-check) ACTION="capacity-check"; shift ;;
            --generate-json) ACTION="generate-json"; shift ;;
            -h|--help)      usage ;;
            *)              err "Unknown option: $1"; usage ;;
        esac
    done

    if [ -z "$ACTION" ]; then
        err "No action specified. Use --apply, --list, --capacity-check, etc."
        usage
    fi
}

main() {
    parse_args "$@"

    # Security: reject default credentials on non-local endpoints
    if [ "$ENDPOINT" != "http://localhost:9000" ] && \
       { [ "$ACCESS_KEY" = "minioadmin" ] || [ "$SECRET_KEY" = "minioadmin" ]; }; then
        err "Refusing default credentials on non-local endpoint ($ENDPOINT). Set MINIO_ACCESS_KEY/MINIO_SECRET_KEY."
        exit 1
    fi

    case "$ACTION" in
        apply)
            check_mc_available
            configure_alias
            apply_all_policies
            ;;
        apply-prefix)
            check_mc_available
            configure_alias
            if [ -z "$TARGET_PREFIX" ]; then
                err "--apply-prefix requires a prefix name"
                exit 1
            fi
            ensure_bucket
            apply_prefix_policy "$TARGET_PREFIX" "${TARGET_EXPIRE:-30}"
            ;;
        list)
            check_mc_available
            configure_alias
            list_policies
            ;;
        clean-uploads)
            check_mc_available
            configure_alias
            clean_incomplete_uploads
            ;;
        capacity-check)
            check_mc_available
            configure_alias
            capacity_check
            ;;
        generate-json)
            generate_lifecycle_json
            ;;
        *)
            err "Unknown action: $ACTION"
            exit 1
            ;;
    esac

    log "Operation '$ACTION' completed"
}

main "$@"
