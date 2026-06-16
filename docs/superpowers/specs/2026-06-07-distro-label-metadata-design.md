# Distro Label Metadata Design

**Date:** 2026-06-07  
**Scope:** Add a stable per-host distro label to benchmark metadata so the Quarto article can show the real operating system name instead of a normalized base distro.

## Goal

Record a human-readable distro label for every benchmark host in `metadata.json`, then use that label throughout the article and summaries.

## Architecture

Introduce a host-level override field named `distro_label`. Benchmark setup will copy that field into `metadata.json` when present, and fall back to `ansible_distribution` when absent. The Quarto article will consume `distro_label` as the primary display label for OS comparisons and dataset summaries.

## Data Model

Each host gets a label such as:
- `Gentoo`
- `CachyOS rolling`
- `Manjaro Linux 26.1.0-pre`
- `elementary OS 8`

The label is a presentation field, not a new classification system. The existing `os` and `os_family` metadata stay unchanged for filtering and compatibility.

## Files

- Modify: `roles/run_benchmarks/tasks/setup.yml`
  - Add `distro_label` to `run_benchmarks_metadata`.
- Modify: host-specific vars files under `host_vars/`
  - Add `distro_label` overrides for hosts that need a label different from `ansible_distribution`.
- Modify: `scripts/benchmarks_article_data.py`
  - Carry `distro_label` through into article rows.
- Modify: `docs/benchmarks-article/index.qmd`
  - Use `distro_label` in dataset summary and per-category OS comparisons.
- Modify: `tests/unit/test_benchmarks_article_data.py`
  - Verify labels are preserved from metadata and exposed to the article loader.

## Behavior

1. If a host has `distro_label` in host vars, metadata should store that exact value.
2. If no override exists, metadata should use `ansible_distribution`.
3. The article should show `distro_label` wherever the page currently displays OS names.
4. Existing filters and grouping can still use `os` / `os_family`; only display labels change.

## Error Handling

- Missing override data must not fail the benchmark run.
- If a host is missing a custom label, the fallback label should still produce a usable article.
- If metadata lacks `distro_label`, the article loader should derive a safe fallback from `os`.

## Testing

- Add a unit test that `load_benchmark_rows()` preserves `distro_label` from metadata.
- Add a unit test that a host with `os: Archlinux` and `distro_label: CachyOS rolling` shows the custom label.
- Render the Quarto article and confirm the dataset summary and OS charts use the new label field.

## Scope Boundaries

Included:
- Host-level distro labels in benchmark metadata.
- Article display updates.

Excluded:
- Changing how benchmark results are collected.
- Reclassifying operating systems in the benchmark execution logic.
- Adding new external inventory sources.
