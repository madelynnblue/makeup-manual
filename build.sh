#!/usr/bin/env bash
# Rebuild the readable HTML edition from the scanned source PDF.
#
#   ./build.sh [path/to/source.pdf]
#
# Stages:
#   1. render every PDF page to JPEG (200 dpi)
#   2. compile the Swift page scanner (Vision OCR + picture detection)
#   3. scan all pages in parallel -> work/json/NNN.json + work/images
#   4. assemble ./index.html, ./assets/book.css, ./assets/book.js
#
# The generated page is written to the repository root, which is exactly what
# GitHub Pages publishes. Requires macOS (Vision/AppKit), poppler and Xcode
# command line tools, plus /usr/share/dict/web2 for hyphenation lookups.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PDF="${1:-$ROOT/source.pdf}"
DPI="${DPI:-200}"
JOBS="${JOBS:-8}"
WORK="$ROOT/work"

cd "$ROOT"

if [ ! -f "$PDF" ]; then
  echo "source PDF not found: $PDF" >&2
  echo "usage: $0 [path/to/source.pdf]" >&2
  exit 1
fi

echo "==> rendering pages at ${DPI} dpi"
rm -rf "$WORK"
mkdir -p "$WORK/pages" "$WORK/images" "$WORK/json" assets/images assets/pages
pdftoppm -r "$DPI" -jpeg -jpegopt quality=92 "$PDF" "$WORK/pages/page"

echo "==> compiling the page scanner"
swiftc -O -module-cache-path "$WORK/.modulecache" -target arm64-apple-macos14.0 \
  tools/scan.swift -o "$WORK/scan"

echo "==> scanning $(ls "$WORK"/pages/*.jpg | wc -l | tr -d ' ') pages"
ls "$WORK"/pages/*.jpg | sed 's#.*/page-##; s#\.jpg##' \
  | xargs -P "$JOBS" -I{} "$WORK/scan" "$WORK/pages/page-{}.jpg" {} "$WORK/images" "$WORK/json/{}.json"

echo "==> copying page facsimiles"
cp "$WORK"/pages/*.jpg assets/pages/

echo "==> assembling HTML"
OUT_DIR="$(mktemp -d)" python3 tools/build_site.py --json "$WORK/json" --out "$ROOT"

echo "==> copying illustrations"
cp "$WORK"/images/*.jpg assets/images/

echo
echo "done: $ROOT/index.html"
