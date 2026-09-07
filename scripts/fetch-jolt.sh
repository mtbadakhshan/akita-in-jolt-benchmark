#!/usr/bin/env bash
set -euo pipefail

ROOT_COMMIT=00610882ef303e8a6b5b0d055a62aad3b96574bd
JOLT_COMMIT=8ba924aff76eb812c6e1f75dcb96496bfa5c76f9
DEST=${1:-third_party/jolt-cpp}

if [[ -e "$DEST" ]]; then
  echo "Destination already exists: $DEST" >&2
  exit 1
fi

git clone --filter=blob:none https://github.com/snarkify/jolt-cpp.git "$DEST"
git -C "$DEST" checkout --detach "$ROOT_COMMIT"
git -C "$DEST" submodule update --init third-party/xbyak

# Pin explicitly rather than trusting a moving submodule branch.
git clone https://github.com/LayerZero-Research/jolt.git "$DEST/third-party/jolt"
git -C "$DEST/third-party/jolt" checkout --detach "$JOLT_COMMIT"

python3 "$(cd "$(dirname "$0")" && pwd)/instrument.py" "$DEST"
cat > "$DEST/.benchmark-source.json" <<EOF
{"jolt_commit":"$ROOT_COMMIT","jolt_submodule_commit":"$JOLT_COMMIT"}
EOF
echo "Prepared pinned Jolt source at $DEST"
