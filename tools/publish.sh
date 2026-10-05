#!/usr/bin/env bash
# Commit the generated site and publish it.
#
#   ./tools/publish.sh "message"
#
# GitHub Pages serves this repository's root, so publishing means committing
# index.html and assets/ and pushing to main. The deploy workflow in
# .github/workflows/pages.yml then republishes the site.
#
# If this repository is checked out inside the working tree where the edition
# is built (a sibling "bobbi_work/site"), the built files are copied across
# first, so a publish always ships the newest build.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MESSAGE="${1:-Update the site}"
SOURCE="${SOURCE_DIR:-}"

cd "$ROOT"

if [ -z "$SOURCE" ] && [ -d "$ROOT/../bobbi_work/site" ]; then
  SOURCE="$ROOT/../bobbi_work/site"
fi

if [ -n "$SOURCE" ] && [ -d "$SOURCE" ]; then
  echo "==> syncing the built edition from $SOURCE"
  cp "$SOURCE/index.html" "$ROOT/index.html"
  rm -rf "$ROOT/assets/images" "$ROOT/assets/pages"
  mkdir -p "$ROOT/assets/images" "$ROOT/assets/pages"
  cp "$SOURCE"/assets/book.css "$SOURCE"/assets/book.js "$ROOT/assets/"
  cp "$SOURCE"/assets/images/*.jpg "$ROOT/assets/images/" 2>/dev/null || true
  cp "$SOURCE"/assets/pages/*.jpg "$ROOT/assets/pages/" 2>/dev/null || true

  # keep only the illustrations the page actually references
  python3 - "$ROOT" <<'PY'
import os, re, sys
root = sys.argv[1]
html = open(os.path.join(root, "index.html"), encoding="utf-8").read()
used = set(re.findall(r"assets/images/(page-\d+-\d+\.jpg)", html))
folder = os.path.join(root, "assets", "images")
for name in os.listdir(folder):
    if name not in used:
        os.remove(os.path.join(folder, name))
print(f"    {len(used)} illustrations referenced, {len(os.listdir(folder))} on disk")
PY
fi

git add -A
if git diff --cached --quiet; then
  echo "nothing to publish: the working tree already matches the last commit"
  exit 0
fi

git commit -m "$MESSAGE"
echo "==> pushing to $(git remote get-url origin)"
git push origin HEAD
echo "published; GitHub Pages will redeploy in a moment"
