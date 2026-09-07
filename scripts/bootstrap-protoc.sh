#!/usr/bin/env bash
set -euo pipefail

VERSION=30.2
GRPCURL_VERSION=1.9.3
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

GRPCURL_DEST="$ROOT/.tools/grpcurl"
GRPCURL_ARCHIVE="$ROOT/.tools/grpcurl-${GRPCURL_VERSION}-linux-x86_64.tar.gz"
mkdir -p "$GRPCURL_DEST"
curl -fL \
  "https://github.com/fullstorydev/grpcurl/releases/download/v${GRPCURL_VERSION}/grpcurl_${GRPCURL_VERSION}_linux_x86_64.tar.gz" \
  -o "$GRPCURL_ARCHIVE"
tar -xzf "$GRPCURL_ARCHIVE" -C "$GRPCURL_DEST" grpcurl
rm "$GRPCURL_ARCHIVE"
"$GRPCURL_DEST/grpcurl" -version
