#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-sync}"
DATASET_SELECTOR="${2:-ALL}"
SESSION_NAME="${3:-acl26_stage_${ACTION}_$(date +%Y%m%d_%H%M%S)}"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/artifacts/staging/logs}"
STAGE_PROFILE="${STAGE_PROFILE:-all}"
RCLONE_REMOTE="${RCLONE_REMOTE:-objectstore}"
TOS_BUCKET="${TOS_BUCKET:-example-autoopt-bucket}"
TOS_PREFIX="${TOS_PREFIX:-datasets/autoopt-workspace/ACL26_ADI/Data}"
SOURCE_DATA_ROOT="${SOURCE_DATA_ROOT:-/data/autoopt-workspace/ACL26_ADI/Data}"
TARGET_DATA_ROOT="${TARGET_DATA_ROOT:-/data/autoopt-workspace/ACL26_ADI/Data}"
RCLONE_TRANSFERS="${RCLONE_TRANSFERS:-16}"
RCLONE_CHECKERS="${RCLONE_CHECKERS:-16}"
RCLONE_BUFFER_SIZE="${RCLONE_BUFFER_SIZE:-128M}"
RCLONE_EXTRA_FLAGS="${RCLONE_EXTRA_FLAGS:-}"
DRY_RUN="${DRY_RUN:-0}"
mkdir -p "$LOG_DIR"

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is required to launch background staging jobs" >&2
  exit 2
fi

LOG_PATH="$LOG_DIR/${SESSION_NAME}.log"
SCRIPT_PATH="$PROJECT_ROOT/scripts/stage_acl26_via_rclone.sh"
ENV_PREFIX="STAGE_PROFILE='$STAGE_PROFILE' RCLONE_REMOTE='$RCLONE_REMOTE' TOS_BUCKET='$TOS_BUCKET' TOS_PREFIX='$TOS_PREFIX' SOURCE_DATA_ROOT='$SOURCE_DATA_ROOT' TARGET_DATA_ROOT='$TARGET_DATA_ROOT' RCLONE_TRANSFERS='$RCLONE_TRANSFERS' RCLONE_CHECKERS='$RCLONE_CHECKERS' RCLONE_BUFFER_SIZE='$RCLONE_BUFFER_SIZE' RCLONE_EXTRA_FLAGS='$RCLONE_EXTRA_FLAGS' DRY_RUN='$DRY_RUN'"

tmux has-session -t "$SESSION_NAME" 2>/dev/null && tmux kill-session -t "$SESSION_NAME" || true
tmux new-session -d -s "$SESSION_NAME" "bash -lc \"$ENV_PREFIX bash '$SCRIPT_PATH' '$ACTION' '$DATASET_SELECTOR' > '$LOG_PATH' 2>&1\""

echo "tmux_session=$SESSION_NAME"
echo "log_path=$LOG_PATH"
echo "tail_command=tmux capture-pane -pt '$SESSION_NAME' -S -200"
