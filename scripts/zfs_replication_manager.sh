#!/usr/bin/env bash
# ============================================================================
# zfs_replication_manager.sh — Tranc3 ZFS Replication with Compression
# ============================================================================
#
# Implements ZFS replication strategies with zstd compression for the Tranc3
# ecosystem. Supports incremental replication using bookmarks for stability,
# multiple replication targets, and bandwidth throttling.
#
# Replication Strategies:
#   1. Incremental (default): Only sends changes since last replication
#   2. Full: Complete dataset transfer (initial setup or recovery)
#   3. Differential: Sends changes since a specific snapshot/bookmark
#
# Compression:
#   - zstd (default): Best ratio + speed balance, ZFS-native
#   - lz4: Fastest, lower ratio (for LAN replication)
#   - gzip-N: Higher ratio, slower (for WAN/remote replication)
#
# Zero-Cost: All replication targets are self-hosted (MinIO, Ceph, or
# another ZFS pool on the same NAS or a peer NAS).
#
# Usage:
#   ./zfs_replication_manager.sh --source tank/tranc3 --target backup/tranc3 --replicate incremental
#   ./zfs_replication_manager.sh --source tank/tranc3 --target backup/tranc3 --replicate full
#   ./zfs_replication_manager.sh --source tank/tranc3 --target backup/tranc3 --replicate incremental --compression zstd
#   ./zfs_replication_manager.sh --source tank/tranc3 --target backup/tranc3 --replicate incremental --bandwidth 10m
#   ./zfs_replication_manager.sh --source tank/tranc3 --status
#
# Part of the Tranc3 Adaptive Smart Storage Architecture
# Storage Tier Priority: ZFS(0) → MinIO(1) → Ceph(2) → R2(3) → OCI(4)
# ============================================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
readonly SCRIPT_NAME="$(basename "$0")"
readonly LOCK_FILE="/var/run/${SCRIPT_NAME}.lock"
# Fallback to /run if /var/run doesn't exist (modern systems use /run)
[ -d /var/run ] || LOCK_FILE="/run/${SCRIPT_NAME}.lock"
readonly LOG_TAG="tranc3-zfs-repl"

# Default compression
DEFAULT_COMPRESSION="zstd-fast"

# Replication state directory (tracks last replicated snapshot per dataset)
STATE_DIR="${ZFS_REPL_STATE_DIR:-/var/lib/tranc3/zfs-replication}"
mkdir -p "$STATE_DIR" 2>/dev/null || true

# ── Logging ──────────────────────────────────────────────────────────────────
log()  { logger -t "$LOG_TAG" -p user.info "$@" 2>/dev/null || echo "[INFO]  $*"; }
warn() { logger -t "$LOG_TAG" -p user.warning "$@" 2>/dev/null || echo "[WARN]  $*" >&2; }
err()  { logger -t "$LOG_TAG" -p user.err "$@" 2>/dev/null || echo "[ERROR] $*" >&2; }

# ── Variables ────────────────────────────────────────────────────────────────
SOURCE=""
TARGET=""
REPLICATION_MODE="incremental"
COMPRESSION="$DEFAULT_COMPRESSION"
BANDWIDTH=""
DRY_RUN=false
VERBOSE=false
RECURSIVE=true
VERIFY=true

# ── Lock Management ──────────────────────────────────────────────────────────
acquire_lock() {
    if [ -f "$LOCK_FILE" ]; then
        local pid
        pid="$(cat "$LOCK_FILE" 2>/dev/null || echo "")"
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            err "Another instance is running (PID: $pid). Aborting."
            exit 1
        fi
        rm -f "$LOCK_FILE"
    fi
    echo $$ > "$LOCK_FILE"
    trap 'rm -f "$LOCK_FILE"' EXIT
}

# ── Compression Configuration ────────────────────────────────────────────────
# Maps compression names to zfs send/recv flags
get_send_compression_pipe() {
    # Returns an external compression pipeline command for zfs send output.
    # NOTE: zfs send does NOT support --compress flags. Compression is handled:
    #   1. Via ZFS dataset compression property (see set_dataset_compression)
    #   2. Via external pipe compression for S3/remote replication (this function)
    # For local ZFS-to-ZFS replication, dataset compression property is sufficient.
    local comp="$1"
    case "$comp" in
        zstd|zstd-fast)
            # zstd level 3 — good balance of speed and ratio
            echo "| zstd -3"
            ;;
        zstd-slow|zstd-max)
            # zstd level 19 — maximum compression for WAN/limited bandwidth
            echo "| zstd -19"
            ;;
        lz4)
            echo "| lz4 -1"
            ;;
        gzip|gzip-6)
            echo "| gzip -6"
            ;;
        gzip-9|gzip-max)
            echo "| gzip -9"
            ;;
        none|raw)
            echo ""
            ;;
        *)
            warn "Unknown compression '$comp', defaulting to zstd"
            echo "| zstd -3"
            ;;
    esac
}

# Set ZFS dataset compression property
set_dataset_compression() {
    local dataset="$1"
    local comp="$2"

    # Map to ZFS compression property values
    local zfs_comp
    case "$comp" in
        zstd|zstd-fast)   zfs_comp="zstd-3" ;;
        zstd-slow|zstd-max) zfs_comp="zstd-19" ;;
        lz4)              zfs_comp="lz4" ;;
        gzip|gzip-6)      zfs_comp="gzip-6" ;;
        gzip-9|gzip-max)  zfs_comp="gzip-9" ;;
        none|raw)         zfs_comp="off" ;;
        *)                zfs_comp="zstd-3" ;;
    esac

    if [ "$DRY_RUN" = true ]; then
        log "[DRY-RUN] Would set compression=$zfs_comp on $dataset"
        return 0
    fi

    zfs set compression="$zfs_comp" "$dataset" 2>/dev/null
    log "Set compression=$zfs_comp on $dataset"
}

# ── Bandwidth Throttling ────────────────────────────────────────────────────
get_bandwidth_pipe() {
    # Returns the bandwidth-throttling pipe segment if BANDWIDTH is set.
    # Usage: zfs send ... $(get_bandwidth_pipe) | zfs recv ...
    # NOTE: The pipe must be placed between zfs send and zfs recv.
    if [ -z "$BANDWIDTH" ]; then
        return 1  # No bandwidth limit configured
    fi
    if command -v pv &>/dev/null; then
        echo "pv -L $BANDWIDTH"
        return 0
    elif command -v mbuffer &>/dev/null; then
        echo "mbuffer -r $BANDWIDTH"
        return 0
    else
        warn "Neither pv nor mbuffer found — bandwidth limiting not available"
        return 1
    fi
}

# ── State Management ────────────────────────────────────────────────────────
get_state_file() {
    local source="$1"
    local target="$2"
    # Create a safe filename from source+target
    local key
    key="$(echo "${source}__${target}" | tr '/' '_' | sed 's/[^a-zA-Z0-9_]//g')"
    echo "${STATE_DIR}/${key}.state"
}

save_replication_state() {
    local source="$1"
    local target="$2"
    local snapshot="$3"
    local state_file
    state_file="$(get_state_file "$source" "$target")"

    cat > "$state_file" <<STATEEOF
source=${source}
target=${target}
last_snapshot=${snapshot}
timestamp=$(date -Iseconds)
compression=${COMPRESSION}
STATEEOF
    if [ "$VERBOSE" = true ]; then
        log "Saved replication state: $snapshot → $state_file"
    fi
}

load_replication_state() {
    local source="$1"
    local target="$2"
    local state_file
    state_file="$(get_state_file "$source" "$target")"

    if [ -f "$state_file" ]; then
        grep '^last_snapshot=' "$state_file" | cut -d= -f2
    else
        echo ""
    fi
}

# ── Replication Operations ──────────────────────────────────────────────────

replicate_full() {
    local source="$1"
    local target="$2"

    log "Starting FULL replication: $source → $target"

    # Get latest snapshot on source
    local latest_snap
    latest_snap="$(zfs list -t snapshot -o name -H -s creation -r "$source" 2>/dev/null | tail -1)"

    if [ -z "$latest_snap" ]; then
        err "No snapshots found on source '$source'. Create a snapshot first."
        return 1
    fi

    local send_flags="-Rv"
    local recv_flags="-suvF"

    # Note: Compression is applied via the ZFS dataset property, not zfs send flags.
    # The dataset property was already set by set_dataset_compression() in main().

    if [ "$DRY_RUN" = true ]; then
        log "[DRY-RUN] Would execute: zfs send $send_flags $latest_snap | zfs recv $recv_flags $target"
        return 0
    fi

    log "Sending: $latest_snap → $target (full, dataset compression=$COMPRESSION)"

    # Execute replication (with optional bandwidth throttling)
    local bw_pipe
    bw_pipe="$(get_bandwidth_pipe)" || true

    if [ "$RECURSIVE" = true ]; then
        if [ -n "$bw_pipe" ]; then
            log "Bandwidth throttling: $BANDWIDTH via ${bw_pipe%% *}"
            zfs send $send_flags "$latest_snap" | $bw_pipe | zfs recv $recv_flags "$target"
        else
            zfs send $send_flags "$latest_snap" | zfs recv $recv_flags "$target"
        fi
    else
        if [ -n "$bw_pipe" ]; then
            zfs send -v "$latest_snap" | $bw_pipe | zfs recv -u "$target"
        else
            zfs send -v "$latest_snap" | zfs recv -u "$target"
        fi
    fi

    local rc=$?
    if [ $rc -eq 0 ]; then
        log "Full replication completed: $latest_snap → $target"
        save_replication_state "$source" "$target" "$latest_snap"

        # Verify after replication
        if [ "$VERIFY" = true ]; then
            verify_replication "$source" "$target" "$latest_snap"
        fi
    else
        err "Full replication failed with exit code $rc"
        return $rc
    fi
}

replicate_incremental() {
    local source="$1"
    local target="$2"

    log "Starting INCREMENTAL replication: $source → $target"

    # Find the last replicated snapshot
    local from_snap
    from_snap="$(load_replication_state "$source" "$target")"

    if [ -z "$from_snap" ]; then
        warn "No previous replication state found. Falling back to full replication."
        replicate_full "$source" "$target"
        return $?
    fi

    # Verify the source snapshot still exists
    if ! zfs list -t snapshot -o name -H "$from_snap" &>/dev/null; then
        warn "Previous snapshot '$from_snap' no longer exists. Trying bookmark..."

        # Try using a bookmark instead
        local bookmark_name
        local snap_short="${from_snap#*@}"
        bookmark_name="${source}#${snap_short}"

        if zfs list -t bookmark -o name -H "$bookmark_name" &>/dev/null; then
            log "Using bookmark: $bookmark_name"
            from_snap="$bookmark_name"
        else
            warn "No bookmark either. Falling back to full replication."
            replicate_full "$source" "$target"
            return $?
        fi
    fi

    # Get latest snapshot on source
    local latest_snap
    latest_snap="$(zfs list -t snapshot -o name -H -s creation -r "$source" 2>/dev/null | tail -1)"

    if [ -z "$latest_snap" ]; then
        warn "No snapshots on source. Nothing to replicate."
        return 0
    fi

    # Skip if already up to date
    if [ "$from_snap" = "$latest_snap" ]; then
        log "Already up to date: $latest_snap"
        return 0
    fi

    local send_flags="-Rv"
    local recv_flags="-suv"

    # Note: Compression is applied via the ZFS dataset property, not zfs send flags.
    # -I flag: send all intermediary snapshots from $from_snap to $latest_snap
    # This is correct for recursive replication to ensure child datasets are
    # properly replicated with all intermediates included.

    if [ "$DRY_RUN" = true ]; then
        log "[DRY-RUN] Would execute: zfs send $send_flags -I $from_snap $latest_snap | zfs recv $recv_flags $target"
        return 0
    fi

    log "Sending incremental: $from_snap → $latest_snap (dataset compression=$COMPRESSION)"

    # Execute incremental replication (with optional bandwidth throttling)
    local bw_pipe
    bw_pipe="$(get_bandwidth_pipe)" || true

    if [ "$RECURSIVE" = true ]; then
        if [ -n "$bw_pipe" ]; then
            log "Bandwidth throttling: $BANDWIDTH via ${bw_pipe%% *}"
            zfs send $send_flags -I "$from_snap" "$latest_snap" | $bw_pipe | zfs recv $recv_flags "$target"
        else
            zfs send $send_flags -I "$from_snap" "$latest_snap" | zfs recv $recv_flags "$target"
        fi
    else
        if [ -n "$bw_pipe" ]; then
            zfs send -v -I "$from_snap" "$latest_snap" | $bw_pipe | zfs recv -u "$target"
        else
            zfs send -v -I "$from_snap" "$latest_snap" | zfs recv -u "$target"
        fi
    fi

    local rc=$?
    if [ $rc -eq 0 ]; then
        log "Incremental replication completed: $from_snap → $latest_snap"
        save_replication_state "$source" "$target" "$latest_snap"

        if [ "$VERIFY" = true ]; then
            verify_replication "$source" "$target" "$latest_snap"
        fi
    else
        err "Incremental replication failed with exit code $rc"
        return $rc
    fi
}

replicate_differential() {
    local source="$1"
    local target="$2"
    local from_snap="$3"

    if [ -z "$from_snap" ]; then
        err "Differential replication requires --from-snapshot"
        return 1
    fi

    log "Starting DIFFERENTIAL replication: $from_snap → latest on $source"

    local latest_snap
    latest_snap="$(zfs list -t snapshot -o name -H -s creation -r "$source" 2>/dev/null | tail -1)"

    if [ -z "$latest_snap" ]; then
        err "No snapshots on source"
        return 1
    fi

    # Note: Compression is applied via the ZFS dataset property

    if [ "$DRY_RUN" = true ]; then
        log "[DRY-RUN] Would execute: zfs send -Rv -I $from_snap $latest_snap | zfs recv -suv $target"
        return 0
    fi

    zfs send -Rv -I "$from_snap" "$latest_snap" | zfs recv -suv "$target"

    local rc=$?
    if [ $rc -eq 0 ]; then
        log "Differential replication completed: $from_snap → $latest_snap"
        save_replication_state "$source" "$target" "$latest_snap"
    else
        err "Differential replication failed"
        return $rc
    fi
}

# ── Verification ─────────────────────────────────────────────────────────────
verify_replication() {
    local source="$1"
    local target="$2"
    local snapshot="$3"

    log "Verifying replication: $source → $target"

    # Check that the target has the snapshot
    local snap_short="${snapshot#*@}"
    local target_snap="${target}@${snap_short}"

    if zfs list -t snapshot -o name -H "$target_snap" &>/dev/null; then
        log "Verification PASSED: $target_snap exists on target"
    else
        warn "Verification WARNING: $target_snap not found on target (may be child dataset)"
    fi

    # Compare snapshot sizes
    local source_size target_size
    source_size="$(zfs list -t snapshot -o used -H -p "$snapshot" 2>/dev/null || echo 0)"
    target_size="$(zfs list -t snapshot -o used -H -p "$target_snap" 2>/dev/null || echo 0)"

    if [ "$VERBOSE" = true ]; then
        log "  Source snapshot size: $source_size bytes"
        log "  Target snapshot size: $target_size bytes"
    fi
}

# ── Replication to MinIO/Ceph (Hybrid) ──────────────────────────────────────
replicate_to_s3() {
    # Replicate ZFS snapshot to S3-compatible storage (MinIO/Ceph/R2)
    # Uses zfs send piped through compression to s3 storage
    local source="$1"
    local s3_endpoint="$2"
    local s3_bucket="$3"
    local s3_prefix="$4"

    if ! command -v aws &>/dev/null && ! command -v mc &>/dev/null; then
        err "Neither aws-cli nor mc (MinIO Client) found. Install one for S3 replication."
        return 1
    fi

    local latest_snap
    latest_snap="$(zfs list -t snapshot -o name -H -s creation -r "$source" 2>/dev/null | tail -1)"

    if [ -z "$latest_snap" ]; then
        err "No snapshots found on $source"
        return 1
    fi

    local snap_short="${latest_snap#*@}"
    local s3_key="${s3_prefix}/${snap_short}.zfs.zst"

    log "Replicating to S3: $latest_snap → s3://${s3_bucket}/${s3_key}"

    if [ "$DRY_RUN" = true ]; then
        log "[DRY-RUN] Would execute: zfs send -Rv $latest_snap | zstd | aws s3 cp - s3://$s3_bucket/$s3_key"
        return 0
    fi

    # Stream ZFS send through zstd compression to S3
    if command -v mc &>/dev/null; then
        zfs send -Rv "$latest_snap" | zstd -3 | mc pipe "${s3_endpoint}/${s3_bucket}/${s3_key}" 2>/dev/null
    else
        zfs send -Rv "$latest_snap" | zstd -3 | aws s3 cp - "s3://${s3_bucket}/${s3_key}" \
            --endpoint-url="$s3_endpoint" 2>/dev/null
    fi

    local rc=$?
    if [ $rc -eq 0 ]; then
        log "S3 replication completed: $latest_snap → s3://${s3_bucket}/${s3_key}"
        save_replication_state "$source" "s3://${s3_bucket}/${s3_prefix}" "$latest_snap"
    else
        err "S3 replication failed"
        return $rc
    fi
}

# ── Status Report ────────────────────────────────────────────────────────────
show_status() {
    local source="$1"

    echo "═══════════════════════════════════════════════════════════════"
    echo "  Tranc3 ZFS Replication Status — $source"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""

    # Source info
    echo "  Source Dataset: $source"
    echo "  Compression:    $COMPRESSION"
    echo ""

    # Snapshots
    echo "  Snapshots (most recent first):"
    echo "  ─────────────────────────────────────────────────────────────"
    zfs list -t snapshot -o name,creation,used -H -s creation -r "$source" 2>/dev/null \
        | tail -10 | tac | while read -r name creation used; do
            printf "  %-55s %s  used: %s\n" "$name" "$creation" "$used"
        done
    echo ""

    # Bookmarks
    echo "  Bookmarks:"
    echo "  ─────────────────────────────────────────────────────────────"
    zfs list -t bookmark -o name,creation -H -r "$source" 2>/dev/null \
        | while read -r name creation; do
            printf "  %-55s %s\n" "$name" "$creation"
        done || echo "  (none)"
    echo ""

    # Replication state
    echo "  Replication State:"
    echo "  ─────────────────────────────────────────────────────────────"
    for state_file in "${STATE_DIR}"/*.state; do
        [ -f "$state_file" ] || continue
        echo "  File: $(basename "$state_file")"
        cat "$state_file" | sed 's/^/    /'
        echo ""
    done || echo "  (no state files)"
    echo ""
}

# ── Main ─────────────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
Tranc3 ZFS Replication Manager with Compression

Usage: $SCRIPT_NAME [OPTIONS]

Options:
  --source DATASET      Source ZFS dataset (required)
  --target DATASET      Target ZFS dataset (for ZFS→ZFS replication)
  --replicate MODE      Replication mode: incremental|full|differential (default: incremental)
  --compression TYPE    Compression: zstd-fast|zstd-slow|lz4|gzip|none (default: zstd-fast)
  --bandwidth RATE      Bandwidth limit (e.g., 10m, 1g) — requires pv or mbuffer
  --from-snapshot SNAP  Base snapshot for differential replication
  --s3-endpoint URL     S3 endpoint for hybrid ZFS→S3 replication
  --s3-bucket BUCKET    S3 bucket name
  --s3-prefix PREFIX    S3 key prefix
  --no-recursive        Don't replicate child datasets
  --no-verify           Skip post-replication verification
  --status              Show replication status for source dataset
  --dry-run             Show what would be done
  --verbose             Enable verbose output
  -h, --help            Show this help

Examples:
  # Full initial replication with zstd
  $SCRIPT_NAME --source tank/tranc3 --target backup/tranc3 --replicate full

  # Incremental daily replication (cron)
  $SCRIPT_NAME --source tank/tranc3 --target backup/tranc3 --replicate incremental

  # Replicate to MinIO (S3-compatible)
  $SCRIPT_NAME --source tank/tranc3 --s3-endpoint http://minio:9000 --s3-bucket tranc3-backup --s3-prefix zfs-repl

  # Show status
  $SCRIPT_NAME --source tank/tranc3 --status
EOF
    exit "${1:-0}"
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --source)        SOURCE="$2"; shift 2 ;;
            --target)        TARGET="$2"; shift 2 ;;
            --replicate)     REPLICATION_MODE="$2"; shift 2 ;;
            --compression)   COMPRESSION="$2"; shift 2 ;;
            --bandwidth)     BANDWIDTH="$2"; shift 2 ;;
            --from-snapshot) FROM_SNAP="$2"; shift 2 ;;
            --s3-endpoint)   S3_ENDPOINT="$2"; shift 2 ;;
            --s3-bucket)     S3_BUCKET="$2"; shift 2 ;;
            --s3-prefix)     S3_PREFIX="$2"; shift 2 ;;
            --no-recursive)  RECURSIVE=false; shift ;;
            --no-verify)     VERIFY=false; shift ;;
            --status)        ACTION="status"; shift ;;
            --dry-run)       DRY_RUN=true; shift ;;
            --verbose)       VERBOSE=true; shift ;;
            -h|--help)       usage ;;
            *)               err "Unknown option: $1"; usage 1 ;;
        esac
    done

    if [ -z "$SOURCE" ]; then
        err "--source is required"
        usage 1
    fi
}

# Global for differential from-snap
FROM_SNAP=""
S3_ENDPOINT=""
S3_BUCKET=""
S3_PREFIX="zfs-repl"
ACTION="replicate"

main() {
    parse_args "$@"
    acquire_lock

    if ! command -v zfs &>/dev/null; then
        err "ZFS commands not found. Is ZFS installed?"
        exit 1
    fi

    case "$ACTION" in
        status)
            show_status "$SOURCE"
            ;;
        replicate)
            # S3 hybrid replication
            if [ -n "${S3_ENDPOINT:-}" ]; then
                replicate_to_s3 "$SOURCE" "$S3_ENDPOINT" "${S3_BUCKET:-tranc3-backup}" "$S3_PREFIX"
            elif [ -z "$TARGET" ]; then
                err "--target or --s3-endpoint is required for replication"
                exit 1
            else
                # ZFS → ZFS replication
                # Ensure target dataset compression is set
                set_dataset_compression "$TARGET" "$COMPRESSION"

                case "$REPLICATION_MODE" in
                    incremental)
                        replicate_incremental "$SOURCE" "$TARGET"
                        ;;
                    full)
                        replicate_full "$SOURCE" "$TARGET"
                        ;;
                    differential)
                        replicate_differential "$SOURCE" "$TARGET" "${FROM_SNAP:-}"
                        ;;
                    *)
                        err "Unknown replication mode: $REPLICATION_MODE"
                        exit 1
                        ;;
                esac
            fi
            ;;
        *)
            err "Unknown action: $ACTION"
            exit 1
            ;;
    esac

    log "Operation completed successfully"
}

main "$@"
