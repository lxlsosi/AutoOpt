#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-AutoOpt}"
REQ_FILE="$(cd "$(dirname "$0")/.." && pwd)/requirements.autoopt.txt"
TORCH_VERSION="${TORCH_VERSION:-2.5.1}"
TORCH_WHL_INDEX="${TORCH_WHL_INDEX:-https://download.pytorch.org/whl/cu121}"
TORCH_WHL_URL="${TORCH_WHL_URL:-https://download.pytorch.org/whl/cu121/torch-2.5.1%2Bcu121-cp310-cp310-linux_x86_64.whl}"
PIP_FLAGS=(--retries 5 --timeout 120 --prefer-binary)

find_conda() {
  if [ -n "${CONDA_BIN:-}" ] && [ -x "${CONDA_BIN:-}" ]; then
    echo "$CONDA_BIN"
    return 0
  fi
  if command -v conda >/dev/null 2>&1; then
    command -v conda
    return 0
  fi
  for candidate in "$HOME/miniconda3/bin/conda" "$HOME/miniforge3/bin/conda" "$HOME/anaconda3/bin/conda" "/root/miniconda3/bin/conda"; do
    if [ -x "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

CONDA_BIN="$(find_conda || true)"

if [ ! -x "$CONDA_BIN" ]; then
  echo "conda not found; set CONDA_BIN or install miniconda/miniforge first" >&2
  exit 1
fi

if ! "$CONDA_BIN" env list | awk '{print $1}' | grep -Fxq "$ENV_NAME"; then
  "$CONDA_BIN" create -y -n "$ENV_NAME" python=3.10 pip
fi

export PIP_DISABLE_PIP_VERSION_CHECK=1

"$CONDA_BIN" run -n "$ENV_NAME" python -m pip install -U pip setuptools wheel
if ! "$CONDA_BIN" run -n "$ENV_NAME" python -c "import torch, sys; sys.exit(0 if torch.__version__ == '${TORCH_VERSION}+cu121' else 1)" >/dev/null 2>&1; then
  "$CONDA_BIN" run -n "$ENV_NAME" python -m pip install "${PIP_FLAGS[@]}" "$TORCH_WHL_URL" || \
    "$CONDA_BIN" run -n "$ENV_NAME" python -m pip install "${PIP_FLAGS[@]}" --extra-index-url "$TORCH_WHL_INDEX" "torch==${TORCH_VERSION}"
fi
"$CONDA_BIN" run -n "$ENV_NAME" python -m pip install "${PIP_FLAGS[@]}" -r "$REQ_FILE"

echo "AutoOpt environment '$ENV_NAME' is ready."
