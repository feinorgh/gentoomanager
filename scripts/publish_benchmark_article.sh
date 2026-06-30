#!/bin/bash
set -e

# Publish benchmark article to GitHub Pages
# Renders Quarto article with existing or new benchmark data,
# and commits HTML to gh-pages branch (sensitive data stays local)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Parse flags
FORCE_BENCHMARKS=0
SKIP_BENCHMARKS=0

while [[ $# -gt 0 ]]; do
  case $1 in
    --force-benchmarks)
      FORCE_BENCHMARKS=1
      shift
      ;;
    --skip-benchmarks)
      SKIP_BENCHMARKS=1
      shift
      ;;
    *)
      echo "Usage: $0 [--force-benchmarks] [--skip-benchmarks]"
      echo ""
      echo "  --force-benchmarks  Always run benchmarks (default: run only if missing)"
      echo "  --skip-benchmarks   Never run benchmarks (use existing data)"
      exit 1
      ;;
  esac
done

cd "$REPO_ROOT"

echo "📊 Publishing benchmark article to GitHub Pages..."
echo ""

# 1. Run benchmarks if needed (generates local data, not committed)
if [ "$SKIP_BENCHMARKS" -eq 1 ]; then
  echo "1️⃣  Skipping benchmarks (--skip-benchmarks)..."
  if [ ! -d "benchmarks/results" ] || [ -z "$(ls -A benchmarks/results 2>/dev/null)" ]; then
    echo "   ⚠️  Warning: benchmarks/results is empty or missing"
    echo "   Article may fail to render if no benchmark data is available"
  fi
elif [ "$FORCE_BENCHMARKS" -eq 1 ] || [ ! -d "benchmarks/results" ] || [ -z "$(ls -A benchmarks/results 2>/dev/null)" ]; then
  echo "1️⃣  Running benchmarks..."
  ansible-playbook playbooks/run_benchmarks.yml
else
  echo "1️⃣  Using existing benchmarks (use --force-benchmarks to re-run)..."
fi

# 2. Render article with data
echo ""
echo "2️⃣  Rendering Quarto article (anonymized)..."
uv sync --group docs

# Generate anonymized host pages
echo "   📝 Generating host detail pages (anonymized)..."
if [ -d "benchmarks/results" ] && [ -n "$(ls -A benchmarks/results 2>/dev/null)" ]; then
  uv run python scripts/benchmarks_article_hosts.py \
    --results benchmarks/results \
    --output docs/benchmarks-article/hosts \
    --anonymize
fi

uv run quarto render docs/benchmarks-article

# 3. Deploy to gh-pages branch
echo ""
echo "3️⃣  Publishing to GitHub Pages..."

# Create or switch to gh-pages-build branch
if git rev-parse --verify gh-pages-build >/dev/null 2>&1; then
  echo "   Switching to existing gh-pages-build branch..."
  git switch gh-pages-build
  git pull origin gh-pages-build || echo "   (no remote tracking)"
else
  echo "   Creating new gh-pages-build branch..."
  git switch --create gh-pages-build
fi

# Add the generated site (with -f to override gitignore)
git add -f docs/benchmarks-article/_site/

# Commit only if there are changes
if git diff --cached --quiet; then
  echo "   ℹ️  No changes to publish"
else
  echo "   📝 Committing rendered article..."
  git commit -m "docs: publish benchmark article

Generated from local benchmark data.
Sensitive benchmark artifacts not included."

  echo "   🚀 Pushing to gh-pages-build..."
  git push origin gh-pages-build
fi

# Switch back to main
echo ""
echo "   ↩️  Returning to main branch..."
git switch main

echo ""
echo "✅ Done! Article published to GitHub Pages."
echo "   Configure repo settings to deploy from gh-pages-build@docs/benchmarks-article/_site/"
