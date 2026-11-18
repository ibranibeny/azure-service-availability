#!/usr/bin/env bash
# Build a ready-to-run zip for one Function app (local build on Linux x64, Python 3.12).
# Usage: scripts/build.sh collector|api <output.zip>
set -euo pipefail
APP="$1"; OUT="$(realpath -m "$2")"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"
"$PY" -c 'import sys; assert sys.version_info[:2] == (3, 12), "Python 3.12 is required (Function apps run 3.12)"'
WORK="$(mktemp -d)"
cp -r "$ROOT/backend/$APP/." "$WORK/"
rm -rf "$WORK/.python_packages" "$WORK/tests"
"$PY" -m pip install --disable-pip-version-check --quiet --no-compile \
  --target "$WORK/.python_packages/lib/site-packages" -r "$WORK/requirements.txt"
find "$WORK" -name "__pycache__" -type d -prune -exec rm -rf {} +
# Compiled wheels must run on the Functions Linux image (glibc 2.36).
if grep -h "^Tag:" "$WORK"/.python_packages/lib/site-packages/*.dist-info/WHEEL 2>/dev/null \
     | grep -E "manylinux_2_(3[7-9]|[4-9][0-9])"; then
  echo "A wheel needs a newer glibc than the Functions image provides." >&2; exit 1
fi
rm -f "$OUT"
(cd "$WORK" && zip -qr -9 "$OUT" .)
echo "Built $OUT ($(du -h "$OUT" | cut -f1))"
rm -rf "$WORK"
