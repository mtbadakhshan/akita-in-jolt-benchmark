#!/usr/bin/env bash
set -euo pipefail

DEST=${1:-third_party/jolt}
# Default is the SHA measured in results/jolt-x86_64. Pass main or latest for tip of origin/main.
PINNED_COMMIT=${2:-7de83dd18839f567e6b88e860d53b0202116654f}

if [[ -e "$DEST" ]]; then
  echo "Destination already exists: $DEST" >&2
  exit 1
fi

git clone --filter=blob:none --branch main https://github.com/a16z/jolt.git "$DEST"
if [[ "$PINNED_COMMIT" == "main" || "$PINNED_COMMIT" == "latest" ]]; then
  ROOT_COMMIT="$(git -C "$DEST" rev-parse HEAD)"
else
  git -C "$DEST" fetch --filter=blob:none origin "$PINNED_COMMIT"
  ROOT_COMMIT="$(git -C "$DEST" rev-parse "$PINNED_COMMIT")"
fi
git -C "$DEST" checkout --detach "$ROOT_COMMIT"
echo "Prepared a16z/jolt at $ROOT_COMMIT in $DEST"
