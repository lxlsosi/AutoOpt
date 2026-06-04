#!/usr/bin/env bash
set -euo pipefail

CONDA_BIN="${CONDA_BIN:-/opt/conda/bin/conda}"
ENV_NAME="${1:-AutoOpt}"
DATA_ROOT="${2:-/data/autoopt-workspace/ACL26_ADI/Data}"

if [ ! -x "$CONDA_BIN" ]; then
  echo "conda not found at $CONDA_BIN" >&2
  exit 1
fi

mkdir -p "$DATA_ROOT"
export HF_HUB_ENABLE_HF_TRANSFER=1

run_download() {
  local repo_id="$1"
  local local_dir="$2"
  echo "downloading $repo_id -> $local_dir"
  "$CONDA_BIN" run -n "$ENV_NAME" hf download "$repo_id" --repo-type dataset --local-dir "$local_dir"
}

cd "$DATA_ROOT"
run_download "UBC-NLP/Casablanca" "Casablanca"
run_download "UBC-NLP/NADI2025_subtask1_SLID" "NADI2025_subtask1_SLID"
run_download "badrex/MADIS5-spoken-arabic-dialects" "MADIS5-spoken-arabic-dialects"
