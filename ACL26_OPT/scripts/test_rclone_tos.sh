#!/usr/bin/env bash
# ============================================================
# test_rclone_tos.sh
# 在 local-controller 上运行，验证 rclone -> object storage 凭证是否可用
# 用法:
#   bash ACL26_OPT/scripts/test_rclone_tos.sh
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONF="$PROJECT_ROOT/config/rclone.objectstore.conf"
RCLONE_BIN="${RCLONE_BIN:-$(command -v rclone 2>/dev/null || echo "$HOME/bin/rclone")}"
BUCKET="${TOS_BUCKET:-example-autoopt-bucket}"
PREFIX="${TOS_PREFIX:-datasets/autoopt-workspace/ACL26_ADI/Data}"
REMOTE="objectstore"

echo "=============================="
echo "  rclone object storage credential debug"
echo "=============================="
echo "Config  : $CONF"
echo "Binary  : $RCLONE_BIN"
echo "Bucket  : $BUCKET"
echo "Prefix  : $PREFIX"
echo ""

# --- 1. 检查 rclone 二进制 ---
if ! command -v "$RCLONE_BIN" &>/dev/null && [ ! -x "$RCLONE_BIN" ]; then
  echo "[FAIL] rclone 未找到，请先运行:"
  echo "       bash ACL26_OPT/scripts/bootstrap_rclone.sh"
  exit 1
fi
echo "[OK] rclone: $("$RCLONE_BIN" version 2>/dev/null | head -1)"

# --- 2. 检查配置文件 ---
if [ ! -f "$CONF" ]; then
  echo "[FAIL] 配置文件不存在: $CONF"
  exit 1
fi
echo "[OK] 配置文件存在"

# --- 3. 列出 remote ---
echo ""
echo "--- 测试 1: listremotes ---"
"$RCLONE_BIN" --config "$CONF" listremotes
echo ""

# --- 4. DNS 解析 (endpoint) ---
ENDPOINT_HOST="${ENDPOINT_HOST:-s3.example.com}"
ENDPOINT_URL="${ENDPOINT_URL:-https://s3.example.com}"
echo "--- 测试 2: DNS 解析 $ENDPOINT_HOST ---"
if host "$ENDPOINT_HOST" &>/dev/null 2>&1; then
  echo "[OK] DNS 正常: $(host "$ENDPOINT_HOST" 2>&1 | head -1)"
else
  echo "[WARN] host 命令不可用，尝试 curl 探测..."
  curl -sv --max-time 5 "$ENDPOINT_URL" 2>&1 | grep -E "Connected|Could not|Failed" | head -5 || true
fi
echo ""

# --- 5. 访问 bucket 根目录 ---
echo "--- 测试 3: lsd $REMOTE:$BUCKET ---"
if "$RCLONE_BIN" --config "$CONF" lsd "$REMOTE:$BUCKET" --timeout 30s --contimeout 10s 2>&1; then
  echo "[OK] Bucket 可访问"
else
  echo "[FAIL] 无法访问 bucket，检查凭证或网络"
fi
echo ""

# --- 6. 访问具体 prefix ---
echo "--- 测试 4: lsd $REMOTE:$BUCKET/$PREFIX (max-depth 1) ---"
if "$RCLONE_BIN" --config "$CONF" lsd "$REMOTE:$BUCKET/$PREFIX" \
    --max-depth 1 --timeout 30s --contimeout 10s 2>&1; then
  echo "[OK] Prefix 路径可访问"
else
  echo "[INFO] Prefix 路径为空或不存在（bucket 本身可访问则说明凭证正常）"
fi
echo ""

echo "=============================="
echo "  调试完成"
echo "=============================="
