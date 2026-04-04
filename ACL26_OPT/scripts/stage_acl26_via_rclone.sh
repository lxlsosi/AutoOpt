#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-verify}"
DATASET_SELECTOR="${2:-ALL}"
RCLONE_BIN="${RCLONE_BIN:-$(command -v rclone || true)}"
RCLONE_REMOTE="${RCLONE_REMOTE:-volctos}"
TOS_BUCKET="${TOS_BUCKET:-momo-test-a100-02}"
TOS_PREFIX="${TOS_PREFIX:-datasets/lv.xiaolei/ACL26_ADI/Data}"
SOURCE_DATA_ROOT="${SOURCE_DATA_ROOT:-/data/lv.xiaolei/ACL26_ADI/Data}"
TARGET_DATA_ROOT="${TARGET_DATA_ROOT:-/data/lv.xiaolei/ACL26_ADI/Data}"
RCLONE_TRANSFERS="${RCLONE_TRANSFERS:-16}"
RCLONE_CHECKERS="${RCLONE_CHECKERS:-16}"
RCLONE_BUFFER_SIZE="${RCLONE_BUFFER_SIZE:-128M}"
RCLONE_EXTRA_FLAGS="${RCLONE_EXTRA_FLAGS:-}"
DRY_RUN="${DRY_RUN:-0}"

usage() {
  cat <<'EOF'
Usage:
  stage_acl26_via_rclone.sh verify [ADI17|MGB2_parquet|ALL]
  stage_acl26_via_rclone.sh upload [ADI17|MGB2_parquet|ALL]
  stage_acl26_via_rclone.sh materialize [ADI17|MGB2_parquet|ALL]
  stage_acl26_via_rclone.sh sync [ADI17|MGB2_parquet|ALL]

Environment:
  RCLONE_REMOTE=volctos
  TOS_BUCKET=momo-test-a100-02
  TOS_PREFIX=datasets/lv.xiaolei/ACL26_ADI/Data
  SOURCE_DATA_ROOT=/data/lv.xiaolei/ACL26_ADI/Data
  TARGET_DATA_ROOT=/data/lv.xiaolei/ACL26_ADI/Data
EOF
}

if [ -z "$RCLONE_BIN" ]; then
  echo "rclone is not installed or not on PATH" >&2
  exit 2
fi

case "$ACTION" in
  verify|upload|materialize|sync) ;;
  *)
    usage >&2
    exit 1
    ;;
esac

case "$DATASET_SELECTOR" in
  ADI17)
    DATASETS=("ADI17")
    ;;
  MGB2_parquet)
    DATASETS=("MGB2_parquet")
    ;;
  ALL)
    DATASETS=("ADI17" "MGB2_parquet")
    ;;
  *)
    echo "unsupported dataset selector: $DATASET_SELECTOR" >&2
    exit 1
    ;;
esac

remote_uri() {
  local relative_path="$1"
  printf '%s:%s/%s/%s' "$RCLONE_REMOTE" "$TOS_BUCKET" "$TOS_PREFIX" "$relative_path"
}

local_dataset_root() {
  local dataset_name="$1"
  local base_root="$2"
  printf '%s/%s' "$base_root" "$dataset_name"
}

copy_flags=(
  copy
  -P
  "--transfers=${RCLONE_TRANSFERS}"
  "--checkers=${RCLONE_CHECKERS}"
  "--buffer-size=${RCLONE_BUFFER_SIZE}"
)

if [ "$DRY_RUN" = "1" ]; then
  copy_flags+=(--dry-run)
fi

if [ -n "$RCLONE_EXTRA_FLAGS" ]; then
  # shellcheck disable=SC2206
  extra_flags=($RCLONE_EXTRA_FLAGS)
  copy_flags+=("${extra_flags[@]}")
fi

echo "verifying TOS access: ${RCLONE_REMOTE}:${TOS_BUCKET}"
"$RCLONE_BIN" lsd "${RCLONE_REMOTE}:${TOS_BUCKET}" >/dev/null

run_upload() {
  local dataset_name="$1"
  local source_root
  source_root="$(local_dataset_root "$dataset_name" "$SOURCE_DATA_ROOT")"
  if [ ! -d "$source_root" ]; then
    echo "source dataset path missing: $source_root" >&2
    exit 3
  fi
  echo "uploading $dataset_name from $source_root to $(remote_uri "$dataset_name")"
  "$RCLONE_BIN" "${copy_flags[@]}" "$source_root" "$(remote_uri "$dataset_name")"
}

run_materialize() {
  local dataset_name="$1"
  local target_root
  target_root="$(local_dataset_root "$dataset_name" "$TARGET_DATA_ROOT")"
  mkdir -p "$target_root"
  echo "materializing $dataset_name from $(remote_uri "$dataset_name") to $target_root"
  "$RCLONE_BIN" "${copy_flags[@]}" "$(remote_uri "$dataset_name")" "$target_root"
}

run_verify() {
  local dataset_name="$1"
  local remote_root target_root file_count
  remote_root="$(remote_uri "$dataset_name")"
  target_root="$(local_dataset_root "$dataset_name" "$TARGET_DATA_ROOT")"
  echo "dataset=$dataset_name"
  echo "remote_root=$remote_root"
  "$RCLONE_BIN" lsd "$remote_root" | head -20 || true
  if [ -d "$target_root" ]; then
    file_count="$(find "$target_root" -type f | wc -l | tr -d ' ')"
    echo "local_target_root=$target_root"
    echo "local_file_count=$file_count"
  else
    echo "local_target_root_missing=$target_root"
  fi
}

for dataset_name in "${DATASETS[@]}"; do
  case "$ACTION" in
    verify)
      run_verify "$dataset_name"
      ;;
    upload)
      run_upload "$dataset_name"
      ;;
    materialize)
      run_materialize "$dataset_name"
      ;;
    sync)
      run_upload "$dataset_name"
      run_materialize "$dataset_name"
      ;;
  esac
done
