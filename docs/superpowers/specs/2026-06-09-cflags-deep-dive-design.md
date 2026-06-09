# CFLAGS Deep-Dive for Gentoo Benchmark Article (Design)

## Goal

Add a focused, data-driven deep-dive in the benchmark article that explains how key CFLAGS dimensions affect Gentoo benchmark outcomes, especially `-march=native` vs more generic flags, plus optimization-related flags (`-O*`, LTO, PGO, Graphite).

## Scope

In scope:
- Article-side analysis and presentation only.
- Parsing and normalization of existing Gentoo flag metadata already present in benchmark results.
- Aggregate and per-category CFLAGS effect visualizations and interpretation text.

Out of scope:
- Benchmark collection pipeline changes.
- Adding new benchmark measurements.
- Non-Gentoo flag modeling.

## Constraints and Assumptions

- Existing benchmark metrics are wall-clock time (`mean_s`), so lower is better.
- Causality cannot be proven from this dataset; results are comparative and observational.
- Flag parsing must be conservative and string-evidence based.
- Existing cross-OS and per-category sections must remain intact.

## Architecture

### 1. New helper module

Create `scripts/benchmarks_cflags_analysis.py` to keep parsing and normalization logic out of `index.qmd`.

Primary responsibilities:
- Parse CFLAGS/common flags text into normalized dimensions.
- Expose enrichment helpers that return dataframe-ready columns for article usage.

### 2. Article integration

Update `docs/benchmarks-article/index.qmd` to:
- Enrich Gentoo rows with parsed CFLAGS dimensions via the new helper.
- Add a dedicated “CFLAGS Deep-Dive” section after current Gentoo tuning focus.
- Render new tables/charts plus interpretation callouts.

## Data Model (Normalized Dimensions)

For each Gentoo row, derive:
- `march_class`
  - `native_like`: `-march=native` or host-specific microarch targeting.
  - `generic_like`: generic targets (e.g. `x86-64`, `x86-64-v2/v3`, or no explicit host-specific target).
  - `unknown`.
- `opt_level`
  - `O2`, `O3`, `Ofast`, `other`, `unknown`.
- `lto_mode`
  - `off`, `on`, `auto`, `thin`, `other`.
- `pgo_mode`
  - `off`, `generate`, `use`, `both_or_other`.
- `graphite_mode`
  - `on`, `off`.

Parsing rules:
- Use explicit string token detection only.
- If conflicting flags exist, classify as `both_or_other`/`other` (not guessed).
- Missing values become `unknown`/`off` per dimension semantics.

## Article Outputs

### A. CFLAGS Dimension Coverage

A compact table showing Gentoo hosts with:
- host alias
- virtualization host CPU label
- parsed dimensions (`march_class`, `opt_level`, `lto_mode`, `pgo_mode`, `graphite_mode`)
- expanded CFLAGS summary

Purpose: confirm dataset coverage and detect imbalance before interpretation.

### B. Aggregate CFLAGS Effect (all benchmark samples)

For each selected dimension, show group medians and relative deltas:
- `native_like` vs `generic_like`
- optimization-level groups
- LTO, PGO, Graphite groups

Presentation:
- bar charts with sample count annotations
- normalized-to-best ratio where useful

### C. Per-category CFLAGS Effect

Per benchmark category, compare group medians for each dimension:
- heatmap or grouped bars for compact scanning
- sorted by strongest absolute effect size

### D. Interpretation Block

For each dimension, include:
- observed direction and approximate magnitude
- spread/stability context (stddev or IQR)
- where effect is strongest/weakest by category
- confounder caveats (CPU generation, virtualization host, package/version mix)

## Error Handling and Robustness

- If a dimension has insufficient diversity (single group), show a “not enough variation” note instead of a misleading chart.
- If Gentoo rows are missing for a category, keep current graceful no-data handling.
- Do not fail article render on sparse CFLAGS coverage; degrade presentation gracefully.

## Testing Strategy

Add `tests/unit/test_benchmarks_cflags_analysis.py`:
- `march_class` classification tests (`native_like`, `generic_like`, `unknown`).
- `opt_level` parsing tests for `-O2/-O3/-Ofast` and conflicts.
- `lto_mode` parsing tests (`off/on/auto/thin/other`).
- `pgo_mode` parsing tests (`off/generate/use/both_or_other`).
- `graphite_mode` detection tests.
- edge-case tests for empty/missing flag strings.

Maintain existing article data tests unchanged unless helper integration requires minimal fixture updates.

## Files to Change

- Create: `scripts/benchmarks_cflags_analysis.py`
- Modify: `docs/benchmarks-article/index.qmd`
- Create: `tests/unit/test_benchmarks_cflags_analysis.py`
- Add changelog fragment for user-visible article enhancement

## Success Criteria

- Article contains a dedicated CFLAGS deep-dive section with aggregate and per-category views.
- `-march=native` vs generic analysis is explicit and visible.
- LTO/PGO/Graphite and optimization-level effects are summarized with caveats.
- New parsing helper has unit test coverage.
- Existing article functionality remains intact.
