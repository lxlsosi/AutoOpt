#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT="${1:-/data/lv.xiaolei/ACL26_ADI}"
SEED_HOST="${2:-ECO01}"
SHARED_ROOT="${3:-/data/AutoOpt/ACL26_ADI_source}"
SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=10 -o ClearAllForwardings=yes"

if [ ! -d "$SOURCE_ROOT" ]; then
  echo "source root not found: $SOURCE_ROOT" >&2
  exit 1
fi

echo "staging source tree from $SOURCE_ROOT to $SEED_HOST:$SHARED_ROOT"
echo "this first sync may take a long time because it can include large data files"

ssh $SSH_OPTS "$SEED_HOST" "mkdir -p '$SHARED_ROOT'"
rsync -az --info=progress2 -e "ssh $SSH_OPTS" \
  --exclude ".git" \
  "$SOURCE_ROOT/" "$SEED_HOST:$SHARED_ROOT/"

for host in ECO01 ECO04 ECOschool; do
  if ssh $SSH_OPTS "$host" "test -e '$SHARED_ROOT/ACL' && test -e '$SHARED_ROOT/Data'"; then
    echo "$host can see $SHARED_ROOT"
  else
    echo "warning: $host cannot confirm $SHARED_ROOT yet" >&2
  fi
done

echo "source staging finished"
