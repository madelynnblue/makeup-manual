#!/usr/bin/env bash
# Install a post-commit hook so every commit in this repository is pushed to
# GitHub, which in turn republishes the site. Run once per clone:
#
#   ./tools/install-hooks.sh
#
# Remove it again by deleting .git/hooks/post-commit.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK="$ROOT/.git/hooks/post-commit"

mkdir -p "$ROOT/.git/hooks"
cat > "$HOOK" <<'HOOK_BODY'
#!/usr/bin/env bash
# Push every commit to GitHub so the Pages workflow can redeploy.
# A failed push never fails the commit; it just prints a warning.
branch="$(git symbolic-ref --short HEAD 2>/dev/null || true)"
[ -z "$branch" ] && exit 0
if ! git remote get-url origin >/dev/null 2>&1; then
  exit 0
fi
if ! git push origin "$branch"; then
  echo "post-commit: push failed; run 'git push origin $branch' when back online" >&2
fi
exit 0
HOOK_BODY
chmod +x "$HOOK"
echo "installed $HOOK"
