# Distro Label Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class `distro_label` field to benchmark metadata so the Quarto article shows the real OS name for every host.

**Architecture:** Store the display label as host-specific override data in `host_vars`, copy it into `metadata.json` during benchmark setup, and use that field everywhere the article renders operating-system names. Keep the existing normalized `os` and `os_family` fields for grouping and compatibility; the new label is purely for presentation.

**Tech Stack:** Ansible roles/tasks, Python (`benchmarks_article_data.py`), pandas, Quarto, pytest.

---

## File Structure

- Modify: `roles/run_benchmarks/tasks/setup.yml`
  - Add `distro_label` to the metadata record written to `metadata.json`.

- Create/Modify: host-specific vars files under `host_vars/`
  - Add `distro_label` overrides for hosts whose displayed distro differs from `ansible_distribution` (for example CachyOS, Manjaro Linux, elementary OS).

- Modify: `scripts/benchmarks_article_data.py`
  - Carry `distro_label` through into each long-form article row and stop synthesizing the label from hostname heuristics.

- Modify: `docs/benchmarks-article/index.qmd`
  - Use `distro_label` in dataset summary tables, per-category summaries, and cross-OS charts.

- Modify: `tests/unit/test_benchmarks_article_data.py`
  - Add regression coverage for the new metadata field and its use in the loader.

---

### Task 1: Add failing loader tests for `distro_label`

**Files:**
- Modify: `tests/unit/test_benchmarks_article_data.py`
- Test: `tests/unit/test_benchmarks_article_data.py`

- [ ] **Step 1: Write the failing test**

```python
def test_load_benchmark_rows_preserves_distro_label_from_metadata(tmp_path: Path) -> None:
    host_dir = tmp_path / "cachyos-jessica"
    host_dir.mkdir()
    (host_dir / "metadata.json").write_text(
        json.dumps(
            {
                "hostname": "cachyos-jessica",
                "os": "Archlinux",
                "os_version": "rolling",
                "os_family": "Archlinux",
                "distro_label": "CachyOS rolling",
                "versions": [],
            }
        )
    )
    (host_dir / "compression.json").write_text(
        json.dumps({"results": [{"command": "gzip -9", "mean": 1.0, "stddev": 0.1}]})
    )

    rows = bad.load_benchmark_rows(tmp_path, anonymize_hosts=False)

    assert len(rows) == 1
    assert rows[0]["distro_label"] == "CachyOS rolling"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_benchmarks_article_data.py::test_load_benchmark_rows_preserves_distro_label_from_metadata -v`  
Expected: FAIL because `distro_label` is not yet returned by `load_benchmark_rows()`.

- [ ] **Step 3: Write minimal implementation**

```python
rows.append(
    {
        "host": host_alias,
        "os": os_name,
        "os_version": os_version,
        "distro_label": metadata.get("distro_label", os_name),
        "os_family": metadata.get("os_family", "unknown"),
        ...
    }
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_benchmarks_article_data.py::test_load_benchmark_rows_preserves_distro_label_from_metadata -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_benchmarks_article_data.py scripts/benchmarks_article_data.py
git commit -m "tests: cover distro label metadata loading"
```

---

### Task 2: Add `distro_label` to benchmark metadata and host overrides

**Files:**
- Modify: `roles/run_benchmarks/tasks/setup.yml:664-710`
- Create: `host_vars/cachyos-jessica/distro.yml`
- Create: `host_vars/manjaro-justene/distro.yml`
- Create: `host_vars/elementaryos-elen/distro.yml`

- [ ] **Step 1: Write the failing test**

Add a metadata assertion to the loader test so the metadata field is exercised end-to-end:

```python
assert rows[0]["distro_label"] == "CachyOS rolling"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_benchmarks_article_data.py::test_load_benchmark_rows_preserves_distro_label_from_metadata -v`  
Expected: FAIL until benchmark setup writes the field and the host override files exist.

- [ ] **Step 3: Write minimal implementation**

`roles/run_benchmarks/tasks/setup.yml`

```yaml
      distro_label: >-
        {{
          distro_label
          | default(ansible_distribution | default('unknown'))
        }}
```

`host_vars/cachyos-jessica/distro.yml`

```yaml
---
distro_label: "CachyOS rolling"
```

`host_vars/manjaro-justene/distro.yml`

```yaml
---
distro_label: "Manjaro Linux 26.1.0-pre"
```

`host_vars/elementaryos-elen/distro.yml`

```yaml
---
distro_label: "elementary OS 8"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_benchmarks_article_data.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add roles/run_benchmarks/tasks/setup.yml host_vars/cachyos-jessica/distro.yml host_vars/manjaro-justene/distro.yml host_vars/elementaryos-elen/distro.yml
git commit -m "feat: add distro label metadata"
```

---

### Task 3: Switch the Quarto article to `distro_label`

**Files:**
- Modify: `docs/benchmarks-article/index.qmd`

- [ ] **Step 1: Write the failing test**

Use a render-visible assertion in the article code block:

```python
assert "distro_label" in df.columns
```

and update the summary grouping to use the new display field:

```python
summary = (
    df.groupby(["distro_label", "os_family", "host"], as_index=False)
    .agg(
        benchmarks=("benchmark", "count"),
        categories=("category", "nunique"),
        lto_enabled=("lto_enabled", "max"),
        pgo_enabled=("pgo_enabled", "max"),
        graphite_enabled=("graphite_enabled", "max"),
    )
    .sort_values(["distro_label", "host"])
)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `quarto render docs/benchmarks-article/index.qmd`  
Expected: the article still renders with the old labels until the code block is updated.

- [ ] **Step 3: Write minimal implementation**

Replace the current article-side OS display helper with a `distro_display` column:

```python
cat_df["distro_display"] = cat_df["distro_label"].fillna(cat_df["os"])
```

Then use `distro_display` in the per-category groupby and the Dataset Summary table.

- [ ] **Step 4: Run test to verify it passes**

Run: `quarto render docs/benchmarks-article/index.qmd`  
Expected: PASS and the summary / charts show CachyOS, Manjaro Linux, and elementary OS labels.

- [ ] **Step 5: Commit**

```bash
git add docs/benchmarks-article/index.qmd
git commit -m "docs: use distro labels in benchmark article"
```

---

### Task 4: Verify repository checks and rendered output

**Files:**
- Modify: `docs/benchmarks-article/README.md` (only if the render command needs a note)

- [ ] **Step 1: Write the failing check**

Document the intended render command if the README needs it:

```markdown
quarto render docs/benchmarks-article/index.qmd
```

- [ ] **Step 2: Run full validation**

Run:

```bash
uv run pytest tests/unit/ && \
uv run ruff check scripts/ tests/ && \
uv run ruff format --check scripts/ tests/
```

Expected: PASS.

- [ ] **Step 3: Render the article**

Run: `quarto render docs/benchmarks-article/index.qmd`  
Expected: PASS with the updated distro labels in Dataset Summary and per-category sections.

- [ ] **Step 4: Commit**

```bash
git add docs/benchmarks-article/README.md
git commit -m "docs: document distro label rendering"
```

---

## Self-Review

- Spec coverage: `distro_label` metadata, host overrides, loader propagation, and article display all have dedicated tasks.
- Placeholder scan: no TBD/TODO/fill-in language remains.
- Type consistency: `distro_label` is the single new display field throughout the plan; `os` and `os_family` remain unchanged for grouping/compatibility.
