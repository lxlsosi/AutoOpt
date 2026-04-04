#!/usr/bin/env bash
set -euo pipefail

TARGET_HOST="${1:-ECOschool}"
SOURCE_ROOT="${2:-/data/lv.xiaolei/ACL26_ADI}"
TARGET_ROOT="${3:-/data/lv.xiaolei/ACL26_ADI}"
ADI17_TRAIN_SHARDS="${ADI17_TRAIN_SHARDS:-4}"
ADI17_TRAIN_SAMPLES_PER_FILE="${ADI17_TRAIN_SAMPLES_PER_FILE:-1500}"
MGB2_TRAIN_FILES="${MGB2_TRAIN_FILES:-30}"
MGB2_TRAIN_SAMPLES_PER_FILE="${MGB2_TRAIN_SAMPLES_PER_FILE:-50}"
SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=10 -o ClearAllForwardings=yes"
STAGE_ROOT="${STAGE_ROOT:-/tmp/acl26_eco_pilot_stage}"

if [ ! -d "$SOURCE_ROOT/ACL" ]; then
  echo "source ACL root not found: $SOURCE_ROOT/ACL" >&2
  exit 1
fi

rm -rf "$STAGE_ROOT"
mkdir -p "$STAGE_ROOT"

/home/user/miniconda3/bin/conda run -n AutoOpt python ACL26_OPT/scripts/build_eco_pilot_stage.py \
  --source-root "$SOURCE_ROOT" \
  --stage-root "$STAGE_ROOT" \
  --adi17-train-shards "$ADI17_TRAIN_SHARDS" \
  --adi17-train-samples-per-file "$ADI17_TRAIN_SAMPLES_PER_FILE" \
  --mgb2-train-files "$MGB2_TRAIN_FILES" \
  --mgb2-train-samples-per-file "$MGB2_TRAIN_SAMPLES_PER_FILE"

ssh $SSH_OPTS "$TARGET_HOST" "rm -rf '$TARGET_ROOT/ACL' '$TARGET_ROOT/Data/ADI17' '$TARGET_ROOT/Data/MGB2_parquet' && mkdir -p '$TARGET_ROOT'"
rsync -az -e "ssh $SSH_OPTS" "$SOURCE_ROOT/ACL/" "$TARGET_HOST:$TARGET_ROOT/ACL/"
rsync -az -e "ssh $SSH_OPTS" "$STAGE_ROOT/Data/" "$TARGET_HOST:$TARGET_ROOT/Data/"

mapfile -t adi17_train_files < <(find "$STAGE_ROOT/Data/ADI17/data" -maxdepth 1 -name 'train-*.parquet' | sort)
mapfile -t mgb2_train_files < <(find "$STAGE_ROOT/Data/MGB2_parquet/train" -maxdepth 1 -name 'train-*.parquet' | sort)

echo "staged pilot data to $TARGET_HOST:$TARGET_ROOT"
echo "ADI17 train shards: ${#adi17_train_files[@]}"
echo "MGB2 train files: ${#mgb2_train_files[@]}"
