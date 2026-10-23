#!/bin/sh
# Builds dist/OriginalAccent-Setup-<version>.exe with NSIS (works on Linux, macOS or Windows).
# Fetches the pinned Windows build of uv into installer/bin if it isn't there.
set -e
cd "$(dirname "$0")"
UV_VERSION=0.9.5
if [ ! -f bin/uv.exe ]; then
  mkdir -p bin
  curl -sSL -o bin/uv.zip "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-pc-windows-msvc.zip"
  unzip -o -q bin/uv.zip uv.exe -d bin && rm bin/uv.zip
fi
V=$(python3 -c "import re;print(re.search(r'\"(.+)\"',open('../original_accent/__init__.py').read()).group(1))")
mkdir -p ../dist
makensis -V2 -DVERSION="$V" original-accent.nsi
echo "Built dist/OriginalAccent-Setup-$V.exe"
