#!/usr/bin/env bash
set -euo pipefail

DEST=${1:-third_party/jolt}

if [[ -e "$DEST" ]]; then
  echo "Destination already exists: $DEST" >&2
  exit 1
fi

git clone --filter=blob:none --branch main https://github.com/a16z/jolt.git "$DEST"
ROOT_COMMIT="$(git -C "$DEST" rev-parse HEAD)"
git -C "$DEST" checkout --detach "$ROOT_COMMIT"
echo "Prepared a16z/jolt main at $ROOT_COMMIT in $DEST"
