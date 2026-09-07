#!/usr/bin/env bash
set -euo pipefail

VERSION=30.2
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/.tools/protoc"
ARCHIVE="$ROOT/.tools/protoc-${VERSION}-linux-x86_64.zip"

mkdir -p "$ROOT/.tools"
curl -fL \
  "https://github.com/protocolbuffers/protobuf/releases/download/v${VERSION}/protoc-${VERSION}-linux-x86_64.zip" \
  -o "$ARCHIVE"
rm -rf "$DEST"
python3 - "$ARCHIVE" "$DEST" <<'PY'
from pathlib import Path
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1]) as archive:
    archive.extractall(sys.argv[2])
Path(sys.argv[2], "bin/protoc").chmod(0o755)
PY
rm "$ARCHIVE"
"$DEST/bin/protoc" --version
