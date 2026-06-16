# Benchmark Category Deep-Dive Design

**Date:** 2026-06-07  
**Scope:** Quarto benchmark article expansion to all benchmark categories with detailed per-category analysis in a multi-page structure.

## Goal

Provide a publication-quality benchmark analysis set where:
1. The article opens with a clear methodology and data-collection description.
2. Every benchmark category gets a dedicated deep-dive page.
3. Each category page includes detailed cross-OS analysis plus Gentoo tuning interpretation (CFLAGS, LTO, PGO, Graphite).

## Architecture

Use a template-driven multi-page Quarto site:
- Keep `index.qmd` as narrative entrypoint and global methodology/data-collection explanation.
- Add one category page per benchmark category under a consistent folder structure.
- Reuse shared Python helpers from `scripts/benchmarks_article_data.py` for data loading, host normalization, and metadata interpretation.
- Centralize repeated category-page logic in a common rendering pattern (same section order, chart types, and caveat blocks).

## File/Component Design

### 1. Site-level content
- `docs/benchmarks-article/index.qmd`
  - Add/expand sections:
    - Benchmark execution methodology
    - Data collection pipeline and metadata provenance
    - How to read/interpret category pages
    - Navigation to per-category deep dives

- `docs/benchmarks-article/_quarto.yml`
  - Add navigation entries for category deep-dive pages.
  - Keep full-width/table-friendly layout settings.

### 2. Category deep-dive pages
- New directory: `docs/benchmarks-article/categories/`
- One `.qmd` page per category (e.g. `compiler.qmd`, `crypto.qmd`, `ffmpeg.qmd`, etc.).
- Standard section contract for every page:
  1. Category purpose and benchmark commands involved
  2. Data coverage summary (hosts/OSes included)
  3. Primary cross-OS comparison visuals
  4. Within-Gentoo tuning comparison visuals
  5. Detailed interpretation and caveats
  6. Practical takeaways

### 3. Data/helper layer
- `scripts/benchmarks_article_data.py`
  - Extend only as needed for reusable per-category aggregation helpers.
  - Preserve anonymization behavior and metadata-driven feature flags.
  - Ensure PGO reflects metadata field when present (already introduced).

## Data Flow

1. Read benchmark result JSON and metadata from `benchmarks/results/<host>/`.
2. Normalize rows into analysis dataframe (host, OS, category, benchmark stats, optimization flags).
3. Filter dataframe by category per page.
4. Render category-specific summary tables and plots.
5. Render narrative interpretation blocks derived from deterministic metrics (avoid ad-hoc/manual values).

## Error Handling & Edge Cases

- Missing dataset: fail early with explicit message already used in article.
- Missing category data:
  - Render explicit “no data for this category” block instead of hard failure.
- Missing metadata fields:
  - Use safe defaults (`False` for optimization booleans, empty string for optional strings) and annotate limitations in page caveats.
- Host anonymization:
  - Continue honoring `QUARTO_BENCHMARKS_ANONYMIZE` default-on behavior.

## Testing Strategy

1. **Unit tests** (`tests/unit/test_benchmarks_article_data.py`)
   - Validate helper behavior used by category pages (including metadata-derived flags and any new aggregation helpers).

2. **Render smoke checks**
   - Local `quarto render docs/benchmarks-article` should succeed with current dataset.
   - Ensure generated category pages include expected headings and at least one visualization/table per category with data.

3. **Repository checks**
   - Existing repository verification commands remain the gate:
     - `uv run pytest tests/unit/`
     - `uv run ansible-lint`
     - `uv run ruff check scripts/ tests/`
     - `uv run ruff format --check scripts/ tests/`

## Scope Boundaries

Included:
- Multi-page deep-dive structure for all available benchmark categories.
- Shared per-category analysis pattern and detailed narrative sections.
- Methodology and data-collection framing in the main entry page.

Excluded:
- New benchmark execution logic.
- Changes to benchmark workloads themselves.
- New external data sources beyond existing `benchmarks/results`.

## Rollout

1. Add methodology/data-collection content to `index.qmd`.
2. Add category page framework and nav entries.
3. Populate all category pages with the standard deep-dive structure.
4. Validate local render and existing test/lint suite.
