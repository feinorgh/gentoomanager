# Benchmark Deep Analysis Design

**Date:** 2026-06-09  
**Scope:** Add a methodology-first, category-level deep analysis to the existing Quarto benchmark article, with qualitative descriptions and metric-aware graphs for each benchmark category.

## Goal

Explain what each benchmark category measures, show how to read it, and provide consistent graphs plus qualitative analysis for every category in the article.

## Architecture

Keep the current single Quarto article and extend it with a methodology/taxonomy section followed by repeated category deep-dive blocks. A small category metadata registry will drive the narrative text, metric direction (`time` vs `rate`), chart labels, and sorting so the article can render each category consistently without hardcoding per-category prose in the template.

The article will continue to load benchmark rows through `scripts/benchmarks_article_data.py`, but the category deep-dive rendering will be driven by a reusable metadata structure rather than ad hoc text. That keeps the analysis readable, makes the “lower is better / higher is better” distinction explicit, and lets the article generate the same visual pattern for each benchmark category.

## Data Model

Each benchmark category will have a registry entry with:
- category name
- human-readable description of what it measures
- metric kind (`time` or `rate`)
- preferred sort direction for charts
- summary text templates for qualitative interpretation

The category registry is presentation metadata. It does not alter benchmark calculations or raw data collection.

## Files

- Modify: `docs/benchmarks-article/index.qmd`
  - Add a methodology/taxonomy section.
  - Add one repeated deep-dive section per benchmark category.
  - Render metric-aware graphs and textual interpretation from the category registry.

- Modify: `scripts/benchmarks_article_data.py`
  - Add reusable helpers if needed to expose category-level summaries or metric orientation to the article.

- Modify: `tests/unit/test_benchmarks_article_data.py`
  - Add regression coverage for any new helper functions or category registry helpers introduced for the article.

## Behavior

1. The article must clearly say when a category is measured as time, where **lower is better**, and when it is measured as rate/throughput, where **higher is better**.
2. Every category section must include:
   - a short “what this measures” paragraph,
   - a cross-OS comparison graph,
   - a per-host distribution graph,
   - a short qualitative interpretation,
   - a caveat/outlier note if the host spread is unusual.
3. The cross-OS graph must sort in the correct direction for the category metric kind.
4. The per-host graph must use the same metric orientation and clearly label units.
5. The article must keep the existing benchmark math intact; this is an analysis and presentation layer only.

## Error Handling

- If a category has no registry entry, render a generic description and a safe default interpretation instead of failing.
- If a category has no rows in the dataset, skip the section or render a short “no data” note.
- If a metric kind is missing, default to `time` and explicitly note that the category was treated as a runtime benchmark.

## Testing

- Add unit tests for any new helper or registry lookup behavior.
- Render the Quarto article and confirm that:
  - the methodology section appears,
  - each category gets a description and graphs,
  - time-based and rate-based categories sort correctly.
- Keep the existing benchmark summary and winner calculations unchanged.

## Scope Boundaries

Included:
- Methodology and benchmark taxonomy narrative.
- Category-level qualitative analysis.
- Metric-aware graphs for every benchmark category.

Excluded:
- Reworking benchmark execution or data collection.
- Splitting the article into separate pages.
- Changing the benchmark results themselves.
