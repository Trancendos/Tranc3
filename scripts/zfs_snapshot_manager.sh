#!/usr/bin/env bash
# ============================================================================
# zfs_snapshot_manager.sh — Tranc3 Adaptive ZFS Auto-Snapshot Manager
# ============================================================================
#
# Implements the best ZFS auto-snapshot strategies for the Tranc3 ecosystem:
#   - Scheduled rotation: hourly (keep 24), daily (keep 7), weekly (keep 4), monthly (keep 6)
#   - Pre/post snapshot hooks for application-consistent snapshots
#   - ZFS bookmark creation for stable replication sources
#   - Recursive dataset snapshots with inheritance
#   - Space-aware: monitors pool capacity and prunes oldest if >80%
#   - Zero-cost: runs entirely on local NAS, no cloud dependencies
#
# Usage:
#   ./zfs_snapshot_manager.sh --pool tank --prefix tranc3 --schedule hourly
#   ./zfs_snapshot_manager.sh --pool tank --prefix tranc3 --schedule daily
#   ./zfs_snapshot_manager.sh --pool tank --prefix tranc3 --schedule weekly
#   ./zfs_snapshot_manager.sh --pool tank --prefix tranc3 --schedule monthly
#   ./zfs_snapshot_manager.sh --pool tank --prefix tranc3 --prune
#   ./zfs_snapshot_manager.sh --pool tank --prefix tranc3 --list
#   ./zfs_snapshot_manager.sh --pool tank --prefix tranc3 --bookmark
#
# Integration (cron):
#   0 *      * * *  root  /opt/tranc3/scripts/zfs_snapshot_manager.sh --pool tank --prefix tranc3 --schedule hourly
#   0 2      * * *  root  /opt/tranc3/scripts/zfs_snapshot_manager.sh --pool tank --prefix tranc3 --schedule daily
#   0 3      * * 0  root  /opt/tranc3/scripts/zfs_snapshot_manager.sh --pool tank --prefix tranc3 --schedule weekly
#   0 4      1 * *  root  /opt/tranc3/scripts/zfs_snapshot_manager.sh --pool tank --prefix tranc3 --schedule monthly
#   0 */6    * * *  root  /opt/tranc3/scripts/zfs_snapshot_manager.sh --pool tank --prefix tranc3 --prune
#
# Part of the Tranc3 Adaptive Smart Storage Architecture
# Storage Tier Priority: ZFS(0) → MinIO(1) → Ceph(2) → R2(3) → OCI(4)
# ============================================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────
readonly SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
readonly LOCK_FILE="/var/run/${SCRIPT_NAME}.lock"
# Fallback to /run if /var/run doesn't exist (modern systems use /run)
[ -d /var/run ] || LOCK_FILE="/run/${SCRIPT_NAME}.lock"
readonly LOG_TAG="tranc3-zfs-snap"

# Retention policy (number of snapshots to keep per schedule type)
readonly KEEP_HOURLY="${ZFS_SNAP_KEEP_HOURLY:-24}"
readonly KEEP_DAILY="${ZFS_SNAP_KEEP_DAILY:-7}"
readonly KEEP_WEEKLY="${ZFS_SNAP_KEEP_WEEKLY:-4}"
readonly KEEP_MONTHLY="${ZFS_SNAP_KEEP_MONTHLY:-6}"

# Capacity thresholds (percentage) — matches SmartStorageOrchestrator
readonly CAPACITY_WARN="${ZFS_CAPACITY_WARN:-80}"
readonly CAPACITY_CRITICAL="${ZFS_CAPACITY_CRITICAL:-95}"

# Default values
POOL=""
PREFIX="tranc3"
SCHEDULE=""
ACTION="snapshot"
DRY_RUN=false
VERBOSE=false
RECURSIVE=true

# ── Logging ──────────────────────────────────────────────────────────────────
log()  { logger -t "$LOG_TAG" -p user.info "$@" 2>/dev/null || echo "[INFO]  $*"; }
warn() { logger -t "$LOG_TAG" -p user.warning "$@" 2>/dev/null || echo "[WARN]  $*" >&2; }
err()  { logger -t "$LOG_TAG" -p user.err "$@" 2>/dev/null || echo "[ERROR] $*" >&2; }

# ── Lock Management ──────────────────────────────────────────────────────────
acquire_lock() {
    if [ -f "$LOCK_FILE" ]; then
        local pid
        pid="$(cat "$LOCK_FILE" 2>/dev/null || echo "")"
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            err "Another instance is running (PID: $pid). Aborting."
            exit 1
        fi
        warn "Stale lock file found (PID: $pid). Removing."
        rm -f "$LOCK_FILE"
    fi
    echo $$ > "$LOCK_FILE"
    trap 'rm -f "$LOCK_FILE"' EXIT
}

# ── Pre-flight Checks ────────────────────────────────────────────────────────
check_zfs_available() {
    if ! command -v zfs &>/dev/null; then
        err "ZFS commands not found. Is ZFS installed?"
        exit 1
    fi
    if ! zfs list -o name "$POOL" &>/dev/null; then
        err "ZFS pool '$POOL' not found or not imported."
        zfs list -o name 2>/dev/null || true
        exit 1
    fi
}

get_pool_capacity() {
    # Returns capacity percentage (0-100) of the pool
    local cap
    cap="$(zfs list -o capacity -H "$POOL" 2>/dev/null | tr -d '%')"
    echo "${cap:-0}"
}

get_pool_available() {
    # Returns available space in bytes
    local avail
    avail="$(zfs list -o available -H -p "$POOL" 2>/dev/null)"
    echo "${avail:-0}"
}

get_datasets() {
    # List the top-level dataset for snapshot creation.
    # When RECURSIVE=true, only the top-level dataset is returned because
    # `zfs snapshot -r` automatically covers all children.
    # This prevents double recursion (snapshots on children already captured
    # by the parent's -r snapshot).
    local dataset_prefix="${POOL}/${PREFIX}"
    if zfs list -o name -H "$dataset_prefix" &>/dev/null; then
        echo "$dataset_prefix"
    else
        warn "Dataset '$dataset_prefix' not found. Using pool root."
        echo "$POOL"
    fi
}

get_all_datasets() {
    # List all datasets explicitly (for per-dataset operations like prune/bookmark)
    local dataset_prefix="${POOL}/${PREFIX}"
    if zfs list -o name -H "$dataset_prefix" &>/dev/null; then
        echo "$dataset_prefix"
        zfs list -o name -H -r "$dataset_prefix" 2>/dev/null | grep -v "^${dataset_prefix}$" || true
    else
        echo "$POOL"
    fi
}

# ── Snapshot Operations ──────────────────────────────────────────────────────
create_snapshot() {
    local dataset="$1"
    local schedule="$2"
    local timestamp
    timestamp="$(date +%Y%m%dT%H%M%S)"
    local snap_name="${dataset}@${PREFIX}-${schedule}-${timestamp}"

    if [ "$DRY_RUN" = true ]; then
        log "[DRY-RUN] Would create snapshot: $snap_name"
        return 0
    fi

    if [ "$VERBOSE" = true ]; then
        log "Creating snapshot: $snap_name"
    fi

    # Pre-snapshot hook: quiesce applications if needed
    run_hook "$dataset" "pre-snapshot" "$schedule" || true

    # Create the snapshot
    # NOTE: When RECURSIVE=true, we only create the snapshot on the top-level
    # dataset with -r flag. This automatically covers all children.
    # We must NOT iterate over child datasets AND use -r (double recursion).
    if [ "$RECURSIVE" = true ]; then
        zfs snapshot -r "$snap_name" 2>/dev/null || true
    else
        zfs snapshot "$snap_name" 2>/dev/null || true
    fi

    local rc=$?
    if [ $rc -eq 0 ]; then
        log "Created snapshot: $snap_name"
    else
        err "Failed to create snapshot: $snap_name"
    fi

    # Post-snapshot hook
    run_hook "$dataset" "post-snapshot" "$schedule" || true

    return $rc
}

create_bookmark() {
    # Create a ZFS bookmark from the latest snapshot of each dataset
    # Bookmarks are stable references for incremental replication
    local dataset="$1"
    local latest_snap

    latest_snap="$(zfs list -t snapshot -o name -H -s creation -r "$dataset" 2>/dev/null | tail -1)"
    if [ -z "$latest_snap" ]; then
        warn "No snapshots found for $dataset. Cannot create bookmark."
        return 1
    fi

    # Extract snapshot short name (part after @)
    local snap_short="${latest_snap#*@}"
    local bookmark_name="${dataset}#${snap_short}"

    if [ "$DRY_RUN" = true ]; then
        log "[DRY-RUN] Would create bookmark: $bookmark_name"
        return 0
    fi

    if zfs bookmark "$latest_snap" "$bookmark_name" 2>/dev/null; then
        log "Created bookmark: $bookmark_name (from $latest_snap)"
    else
        # Bookmark might already exist
        if zfs list -t bookmark -o name -H "$bookmark_name" &>/dev/null; then
            log "Bookmark already exists: $bookmark_name"
        else
            err "Failed to create bookmark: $bookmark_name"
            return 1
        fi
    fi
}

# ── Hook System ──────────────────────────────────────────────────────────────
run_hook() {
    local dataset="$1"
    local hook_type="$2"   # pre-snapshot, post-snapshot
    local schedule="$3"

    local hook_dir="${SCRIPT_DIR}/hooks/${hook_type}"
    if [ -d "$hook_dir" ]; then
        for hook in "$hook_dir"/*.sh; do
            if [ -x "$hook" ]; then
                log "Running ${hook_type} hook: $(basename "$hook")"
                "$hook" "$dataset" "$schedule" || {
                    warn "Hook $(basename "$hook") failed for $dataset"
                }
            fi
        done
    fi
}

# ── Retention & Pruning ─────────────────────────────────────────────────────
get_retention_count() {
    local schedule="$1"
    case "$schedule" in
        hourly)  echo "$KEEP_HOURLY"  ;;
        daily)   echo "$KEEP_DAILY"   ;;
        weekly)  echo "$KEEP_WEEKLY"  ;;
        monthly) echo "$KEEP_MONTHLY" ;;
        *)       echo "$KEEP_DAILY"   ;;
    esac
}

prune_snapshots() {
    local dataset="$1"
    local schedule="$2"
    local keep
    keep="$(get_retention_count "$schedule")"

    # Get all snapshots for this dataset+schedule, oldest first
    local snaps
    snaps="$(zfs list -t snapshot -o name -H -s creation -r "$dataset" 2>/dev/null \
        | grep "@${PREFIX}-${schedule}-" || true)"

    if [ -z "$snaps" ]; then
        return 0
    fi

    local total
    total="$(echo "$snaps" | wc -l)"

    if [ "$total" -le "$keep" ]; then
        if [ "$VERBOSE" = true ]; then
            log "Retention OK: $total ${schedule} snapshots (keep=$keep) for $dataset"
        fi
        return 0
    fi

    local to_delete=$((total - keep))
    log "Pruning $to_delete/${total} ${schedule} snapshots for $dataset (keep=$keep)"

    echo "$snaps" | head -n "$to_delete" | while read -r snap; do
        if [ "$DRY_RUN" = true ]; then
            log "[DRY-RUN] Would destroy: $snap"
        else
            if zfs destroy "$snap" 2>/dev/null; then
                log "Destroyed: $snap"
            else
                err "Failed to destroy: $snap (may have clones/holds)"
            fi
        fi
    done
}

capacity_aware_prune() {
    # Proactive pruning when pool capacity exceeds warning threshold
    # This mirrors SmartStorageOrchestrator's zero-cost capacity enforcement
    local capacity
    capacity="$(get_pool_capacity)"

    if [ "$capacity" -lt "$CAPACITY_WARN" ]; then
        if [ "$VERBOSE" = true ]; then
            log "Pool capacity at ${capacity}% — below warning threshold (${CAPACITY_WARN}%)"
        fi
        return 0
    fi

    warn "Pool capacity at ${capacity}% — exceeds warning threshold (${CAPACITY_WARN}%)"
    log "Starting capacity-aware pruning across all schedules..."

    # Prune most aggressively: start with hourly (most frequent)
    for schedule in hourly daily weekly monthly; do
        local keep_original
        keep_original="$(get_retention_count "$schedule")"

        # Reduce retention by half during capacity pressure
        export "ZFS_SNAP_KEEP_${schedule^^}=$(( keep_original / 2 ))"

        for dataset in $(get_all_datasets); do
            prune_snapshots "$dataset" "$schedule"
        done

        # Restore original
        export "ZFS_SNAP_KEEP_${schedule^^}=$keep_original"

        # Check if we've recovered enough
        capacity="$(get_pool_capacity)"
        if [ "$capacity" -lt "$CAPACITY_WARN" ]; then
            log "Capacity recovered to ${capacity}% after pruning ${schedule} snapshots"
            return 0
        fi
    done

    if [ "$capacity" -ge "$CAPACITY_CRITICAL" ]; then
        err "CRITICAL: Pool capacity at ${capacity}% — even after aggressive pruning!"
        err "Consider migrating data to MinIO/Ceph tier (SmartStorageOrchestrator auto-migration)"
        return 1
    fi

    warn "Capacity at ${capacity}% — above warning but below critical"
    return 0
}

# ── List Snapshots ───────────────────────────────────────────────────────────
list_snapshots() {
    local dataset_prefix="${POOL}/${PREFIX}"

    echo "═══════════════════════════════════════════════════════════════"
    echo "  Tranc3 ZFS Snapshots — ${POOL}"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""

    # Pool info
    local capacity used avail
    capacity="$(get_pool_capacity)"
    used="$(zfs list -o used -H "$POOL" 2>/dev/null || echo 'N/A')"
    avail="$(zfs list -o available -H "$POOL" 2>/dev/null || echo 'N/A')"
    echo "  Pool:       $POOL"
    echo "  Capacity:   ${capacity}%  (Used: $used  Available: $avail)"
    echo "  Thresholds: Warn=${CAPACITY_WARN}%  Critical=${CAPACITY_CRITICAL}%"
    echo ""

    # Summary by schedule type
    for schedule in hourly daily weekly monthly; do
        local keep count
        keep="$(get_retention_count "$schedule")"
        count="$(zfs list -t snapshot -o name -H -r "$dataset_prefix" 2>/dev/null \
            | grep "@${PREFIX}-${schedule}-" | wc -l || echo 0)"
        printf "  %-10s  %3d snapshots  (keep: %d)\n" "$schedule" "$count" "$keep"
    done
    echo ""

    # Detailed snapshot list
    echo "  Recent Snapshots:"
    echo "  ─────────────────────────────────────────────────────────────"
    zfs list -t snapshot -o name,creation,used,refer -H -s creation -r "$dataset_prefix" 2>/dev/null \
        | tail -20 | while read -r name creation used refer; do
            local short_name="${name#*@}"
            printf "  %-50s  created: %s  used: %s\n" "$short_name" "$creation" "$used"
        done
    echo ""

    # Bookmarks
    echo "  Bookmarks:"
    echo "  ─────────────────────────────────────────────────────────────"
    zfs list -t bookmark -o name,creation -H -r "$dataset_prefix" 2>/dev/null \
        | while read -r name creation; do
            local short_name="${name#*#}"
            printf "  %-50s  created: %s\n" "$short_name" "$creation"
        done || echo "  (none)"
    echo ""
}

# ── Main Execution ───────────────────────────────────────────────────────────
usage() {
    local exit_code="${1:-0}"
    cat <<EOF
Tranc3 ZFS Auto-Snapshot Manager

Usage: $SCRIPT_NAME [OPTIONS]

Options:
  --pool POOL         ZFS pool name (required)
  --prefix PREFIX     Dataset prefix (default: tranc3)
  --schedule TYPE     Snapshot schedule: hourly|daily|weekly|monthly
  --prune             Run retention-based pruning
  --capacity-prune    Run capacity-aware pruning
  --bookmark          Create bookmarks from latest snapshots
  --list              List all snapshots and status
  --no-recursive      Don't snapshot child datasets
  --dry-run           Show what would be done without executing
  --verbose           Enable verbose output
  -h, --help          Show this help message

Examples:
  $SCRIPT_NAME --pool tank --prefix tranc3 --schedule hourly
  $SCRIPT_NAME --pool tank --prefix tranc3 --prune --schedule daily
  $SCRIPT_NAME --pool tank --prefix tranc3 --capacity-prune
  $SCRIPT_NAME --pool tank --prefix tranc3 --bookmark
  $SCRIPT_NAME --pool tank --prefix tranc3 --list
EOF
    exit "$exit_code"
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --pool)         POOL="$2"; shift 2 ;;
            --prefix)       PREFIX="$2"; shift 2 ;;
            --schedule)     SCHEDULE="$2"; shift 2 ;;
            --prune)        ACTION="prune"; shift ;;
            --capacity-prune) ACTION="capacity-prune"; shift ;;
            --bookmark)     ACTION="bookmark"; shift ;;
            --list)         ACTION="list"; shift ;;
            --no-recursive) RECURSIVE=false; shift ;;
            --dry-run)      DRY_RUN=true; shift ;;
            --verbose)      VERBOSE=true; shift ;;
            -h|--help)      usage ;;
            *)              err "Unknown option: $1"; usage 1 ;;
        esac
    done

    if [ -z "$POOL" ]; then
        err "--pool is required"
        usage 1
    fi
}

main() {
    parse_args "$@"
    acquire_lock
    check_zfs_available

    case "$ACTION" in
        snapshot)
            if [ -z "$SCHEDULE" ]; then
                err "--schedule is required for snapshot creation"
                exit 1
            fi
            log "Creating ${SCHEDULE} snapshots for ${POOL}/${PREFIX}"
            for dataset in $(get_datasets); do
                create_snapshot "$dataset" "$SCHEDULE"
            done
            # Also create bookmark for replication stability
            if [ "$SCHEDULE" = "daily" ] || [ "$SCHEDULE" = "weekly" ]; then
                for dataset in $(get_all_datasets); do
                    create_bookmark "$dataset"
                done
            fi
            # Auto-prune after creating new snapshot
            for dataset in $(get_all_datasets); do
                prune_snapshots "$dataset" "$SCHEDULE"
            done
            ;;
        prune)
            if [ -z "$SCHEDULE" ]; then
                err "--schedule is required for pruning"
                exit 1
            fi
            log "Pruning ${SCHEDULE} snapshots for ${POOL}/${PREFIX}"
            for dataset in $(get_all_datasets); do
                prune_snapshots "$dataset" "$SCHEDULE"
            done
            ;;
        capacity-prune)
            log "Running capacity-aware pruning for ${POOL}"
            capacity_aware_prune
            ;;
        bookmark)
            log "Creating bookmarks for ${POOL}/${PREFIX}"
            for dataset in $(get_all_datasets); do
                create_bookmark "$dataset"
            done
            ;;
        list)
            list_snapshots
            ;;
        *)
            err "Unknown action: $ACTION"
            exit 1
            ;;
    esac

    log "Operation '$ACTION' completed successfully"
}

main "$@"
