#!/usr/bin/env bash
# publish_quarto_pages.sh — Render the Quarto benchmark article and publish
# the rendered site to the gh-pages-build branch via a git worktree.
#
# The gh-pages-build branch is kept in a separate worktree so the main
# checkout is never switched away from its current branch.
#
# Usage:
#   ./scripts/publish_quarto_pages.sh [--help]
#
# Prerequisites:
#   - uv (Python package manager)
#   - quarto
#   - rsync
#
# Benchmark data (benchmarks/results/) must already exist; this script
# renders from whatever data is present and warns if none is found.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SITE_DIR="$REPO_ROOT/docs/benchmarks-article/_site"
WORKTREE_DIR="/tmp/gm-pages"
PAGES_BRANCH="gh-pages-build"

usage() {
    cat <<EOF
Usage: $(basename "$0") [--help]

Render the Quarto benchmark article and publish to $PAGES_BRANCH.

  Benchmark results in benchmarks/results/ must already exist.
  This script does NOT run benchmarks — it only renders and publishes.

  The rendered site is committed to the '$PAGES_BRANCH' branch via a
  git worktree at $WORKTREE_DIR, so the main checkout is never switched.
EOF
}

die() { echo "ERROR: $*" >&2; exit 1; }

for arg in "$@"; do
    case "$arg" in
        --help|-h) usage; exit 0 ;;
        *) die "Unknown option: $arg" ;;
    esac
done

command -v uv    >/dev/null 2>&1 || die "uv not found"
command -v quarto >/dev/null 2>&1 || die "quarto not found"
command -v rsync >/dev/null 2>&1 || die "rsync not found"

cd "$REPO_ROOT"

# ── 1. Warn if benchmark results are missing ─────────────────────────────────
echo "📊 Checking benchmark data..."
if [[ ! -d "benchmarks/results" ]] || [[ -z "$(ls -A benchmarks/results 2>/dev/null)" ]]; then
    echo "   ⚠️  Warning: benchmarks/results is absent or empty."
    echo "   The article will render with whatever data is already committed."
    echo "   Run the benchmark suite first to generate fresh results."
else
    echo "   ✔  Found results in benchmarks/results/"
fi

# ── 2. Install doc dependencies ───────────────────────────────────────────────
echo ""
echo "📦 Installing doc dependencies..."
uv sync --group docs

# ── 3. Generate anonymized host detail pages ──────────────────────────────────
if [[ -d "benchmarks/results" ]] && [[ -n "$(ls -A benchmarks/results 2>/dev/null)" ]]; then
    echo ""
    echo "📝 Generating anonymized host detail pages..."
    uv run python scripts/benchmarks_article_hosts.py \
        --results benchmarks/results \
        --output docs/benchmarks-article/hosts \
        --anonymize
fi

# ── 4. Render Quarto site (abort on failure) ──────────────────────────────────
echo ""
echo "🔨 Rendering Quarto site..."
uv run quarto render docs/benchmarks-article

[[ -d "$SITE_DIR" ]] || die "Render succeeded but _site/ not found at $SITE_DIR"

# ── 5. Set up the gh-pages-build worktree ────────────────────────────────────
echo ""
echo "🌿 Preparing worktree at $WORKTREE_DIR (branch: $PAGES_BRANCH)..."
git worktree prune

if [[ -d "$WORKTREE_DIR" ]]; then
    actual_branch=$(git -C "$WORKTREE_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
    if [[ "$actual_branch" != "$PAGES_BRANCH" ]]; then
        die "Worktree at $WORKTREE_DIR is on branch '$actual_branch', not '$PAGES_BRANCH'." \
            $'\nRemove it with: git worktree remove --force '"$WORKTREE_DIR"
    fi
    echo "   ✔  Reusing existing worktree"
elif git rev-parse --verify "$PAGES_BRANCH" >/dev/null 2>&1; then
    git worktree add "$WORKTREE_DIR" "$PAGES_BRANCH"
    echo "   ✔  Worktree created from existing branch"
else
    git worktree add -b "$PAGES_BRANCH" "$WORKTREE_DIR"
    echo "   ✔  Worktree created with new branch"
fi

# Sync remote tracking branch so we push cleanly
if git rev-parse --verify "origin/$PAGES_BRANCH" >/dev/null 2>&1; then
    git -C "$WORKTREE_DIR" fetch origin "$PAGES_BRANCH" --quiet || true
fi

# ── 6. Sync rendered site into worktree ──────────────────────────────────────
echo ""
echo "🔄 Syncing rendered site into worktree..."
mkdir -p "$WORKTREE_DIR/docs/benchmarks-article"
rsync -a --delete "$SITE_DIR/" "$WORKTREE_DIR/"

# ── 7. Commit and push ────────────────────────────────────────────────────────
echo ""
cd "$WORKTREE_DIR"
git add -A

if git diff --cached --quiet; then
    echo "ℹ️  No changes since last publish — nothing to commit."
else
    git commit -m "docs: publish Quarto benchmark article

Rendered from local benchmark results (sensitive data excluded)."

    echo "🚀 Pushing to $PAGES_BRANCH..."
    git push origin "$PAGES_BRANCH"
fi

echo ""
echo "✅ Done! Rendered site published to branch '$PAGES_BRANCH'."
echo "   Trigger the GitHub Actions workflow to deploy to GitHub Pages."
