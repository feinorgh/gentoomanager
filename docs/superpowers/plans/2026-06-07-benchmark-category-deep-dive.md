# Benchmark Category Deep-Dive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-page Quarto benchmark report with detailed per-category deep-dives plus a clear methodology/data-collection preface.

**Architecture:** Keep `index.qmd` as the entry page and methodology narrative, then split category analysis into one page per benchmark category under `docs/benchmarks-article/categories/`. Reuse shared Python data-loading logic from `scripts/benchmarks_article_data.py` and keep page logic uniform so every category renders consistent visuals, caveats, and Gentoo-specific interpretation.

**Tech Stack:** Quarto, Python (pandas/plotly), existing `benchmarks_article_data.py`, pytest, ruff, ansible-lint.

---

## File Structure

- Modify: `docs/benchmarks-article/index.qmd`  
  Add the long-form “how benchmarks are run / how data is collected” narrative and links into category deep-dive pages.

- Modify: `docs/benchmarks-article/_quarto.yml`  
  Add navbar/sidebar entries for category pages.

- Create: `docs/benchmarks-article/categories/_category_template.qmd` (optional source template for copy/paste consistency)  
  Defines the standard section contract for each category.

- Create: `docs/benchmarks-article/categories/<category>.qmd` for each benchmark category  
  Category-specific deep-dive pages.

- Modify: `scripts/benchmarks_article_data.py`  
  Add reusable helper functions for category-level aggregation used by all pages.

- Modify/Test: `tests/unit/test_benchmarks_article_data.py`  
  Add/extend tests for any new helper behavior and metadata fallback logic.

---

### Task 1: Add failing tests for category-level aggregation helpers

**Files:**
- Modify: `tests/unit/test_benchmarks_article_data.py`
- Test: `tests/unit/test_benchmarks_article_data.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_category_summary_groups_by_os_and_host():
    rows = [
        {"category": "compiler", "host": "a", "os": "Gentoo", "mean_s": 10.0},
        {"category": "compiler", "host": "a", "os": "Gentoo", "mean_s": 14.0},
        {"category": "compiler", "host": "b", "os": "Debian", "mean_s": 20.0},
    ]
    summary = build_category_summary(rows, "compiler")
    assert len(summary) == 2
    assert summary[0]["category"] == "compiler"
    assert "median_s" in summary[0]


def test_build_category_summary_handles_missing_category():
    rows = [{"category": "crypto", "host": "a", "os": "Gentoo", "mean_s": 1.0}]
    assert build_category_summary(rows, "compiler") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_benchmarks_article_data.py::test_build_category_summary_groups_by_os_and_host tests/unit/test_benchmarks_article_data.py::test_build_category_summary_handles_missing_category -v`  
Expected: FAIL with missing `build_category_summary` (or equivalent assertion failure).

- [ ] **Step 3: Write minimal implementation**

```python
def build_category_summary(rows: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    filtered = [row for row in rows if row.get("category") == category]
    if not filtered:
        return []
    grouped: dict[tuple[str, str], list[float]] = {}
    for row in filtered:
        key = (str(row.get("host", "")), str(row.get("os", "")))
        grouped.setdefault(key, []).append(float(row.get("mean_s", 0.0)))
    summary: list[dict[str, Any]] = []
    for (host, os_name), values in grouped.items():
        values_sorted = sorted(values)
        mid = len(values_sorted) // 2
        median_s = (
            values_sorted[mid]
            if len(values_sorted) % 2 == 1
            else (values_sorted[mid - 1] + values_sorted[mid]) / 2
        )
        summary.append({"category": category, "host": host, "os": os_name, "median_s": median_s})
    return sorted(summary, key=lambda item: (item["os"], item["host"]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_benchmarks_article_data.py::test_build_category_summary_groups_by_os_and_host tests/unit/test_benchmarks_article_data.py::test_build_category_summary_handles_missing_category -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_benchmarks_article_data.py scripts/benchmarks_article_data.py
git commit -m "tests: add category summary helper coverage"
```

---

### Task 2: Add methodology and data-collection narrative to entry page

**Files:**
- Modify: `docs/benchmarks-article/index.qmd`

- [ ] **Step 1: Write the failing content check (manual QA target)**

Add this checklist comment to the top of `index.qmd` while editing:

```markdown
<!-- QA: index must include sections "Benchmark Methodology" and "Data Collection Pipeline" -->
```

- [ ] **Step 2: Run render to verify current doc misses required sections**

Run: `quarto render docs/benchmarks-article/index.qmd`  
Expected: render succeeds, but the required section headers are not yet present.

- [ ] **Step 3: Write minimal implementation**

Insert sections in `index.qmd`:

```markdown
## Benchmark Methodology

Benchmarks are executed via the `roles/run_benchmarks` Ansible role on each VM...

## Data Collection Pipeline

Each host writes `metadata.json` and category result JSON files under `benchmarks/results/<host>/`...
```

- [ ] **Step 4: Run render to verify sections appear**

Run: `quarto render docs/benchmarks-article/index.qmd`  
Expected: PASS and sections are present in rendered output.

- [ ] **Step 5: Commit**

```bash
git add docs/benchmarks-article/index.qmd
git commit -m "docs: add benchmark methodology and data collection narrative"
```

---

### Task 3: Create category-page framework and navigation

**Files:**
- Modify: `docs/benchmarks-article/_quarto.yml`
- Create: `docs/benchmarks-article/categories/_category_template.qmd`
- Create: `docs/benchmarks-article/categories/compiler.qmd`
- Create: `docs/benchmarks-article/categories/crypto.qmd`
- Create: `docs/benchmarks-article/categories/compression.qmd`
- Create: `docs/benchmarks-article/categories/python.qmd`
- Create: `docs/benchmarks-article/categories/ffmpeg.qmd`
- Create: `docs/benchmarks-article/categories/imagemagick.qmd`
- Create: `docs/benchmarks-article/categories/coreutils.qmd`
- Create: `docs/benchmarks-article/categories/opencv.qmd`
- Create: `docs/benchmarks-article/categories/gimp.qmd`
- Create: `docs/benchmarks-article/categories/inkscape.qmd`
- Create: `docs/benchmarks-article/categories/startup.qmd`
- Create: `docs/benchmarks-article/categories/gentoo_build_times.qmd`
- Create: `docs/benchmarks-article/categories/numeric.qmd`
- Create: `docs/benchmarks-article/categories/sqlite.qmd`
- Create: `docs/benchmarks-article/categories/memory.qmd`
- Create: `docs/benchmarks-article/categories/process.qmd`
- Create: `docs/benchmarks-article/categories/disk.qmd`
- Create: `docs/benchmarks-article/categories/linker.qmd`
- Create: `docs/benchmarks-article/categories/boot_time.qmd`
- Create: `docs/benchmarks-article/categories/bash.qmd`
- Create: `docs/benchmarks-article/categories/octave.qmd`

- [ ] **Step 1: Write the failing test (navigation presence check)**

Add expected nav entries in `_quarto.yml` first as a checklist comment:

```yaml
# QA: categories nav must include compiler, crypto, ffmpeg, startup, disk, linker
```

- [ ] **Step 2: Run render to verify pages are currently missing**

Run: `quarto render docs/benchmarks-article`  
Expected: FAIL or missing output pages for categories.

- [ ] **Step 3: Write minimal implementation**

Create one shared category page structure:

```markdown
---
title: "Compiler Deep Dive"
---

```{python}
from pathlib import Path
import pandas as pd
import sys
sys.path.insert(0, str(Path("../../../scripts").resolve()))
from benchmarks_article_data import load_benchmark_rows
rows = load_benchmark_rows(Path("../../../benchmarks/results"))
df = pd.DataFrame(rows)
cat = df[df["category"] == "compiler"].copy()
```

## Category Scope
## Coverage
## Cross-OS Results
## Gentoo Tuning Analysis
## Interpretation and Caveats
```

- [ ] **Step 4: Run render to verify all pages are generated**

Run: `quarto render docs/benchmarks-article`  
Expected: PASS and category pages emitted under `_site/categories/`.

- [ ] **Step 5: Commit**

```bash
git add docs/benchmarks-article/_quarto.yml docs/benchmarks-article/categories/
git commit -m "docs: add multi-page category deep-dive framework"
```

---

### Task 4: Implement detailed analysis sections per category

**Files:**
- Modify: `docs/benchmarks-article/categories/*.qmd`

- [ ] **Step 1: Write failing page checks (content contract)**

For one category file (e.g. `compiler.qmd`) add required section checklist:

```markdown
<!-- QA contract:
1) Category purpose
2) Data coverage
3) Cross-OS chart(s)
4) Gentoo tuning chart(s)
5) Detailed interpretation
6) Caveats + takeaways
-->
```

- [ ] **Step 2: Run render and inspect page to confirm missing sections**

Run: `quarto render docs/benchmarks-article/categories/compiler.qmd`  
Expected: page renders but contract sections are incomplete before implementation.

- [ ] **Step 3: Write minimal implementation**

Apply this pattern to each category page:

```markdown
## Category Purpose
Text explaining what this benchmark category measures and why it matters.

## Data Coverage
```{python}
cat.groupby(["os", "host"], as_index=False)["benchmark"].count()
```

## Cross-OS Results
```{python}
import plotly.express as px
fig = px.box(cat, x="os", y="mean_s", color="os", points="all")
fig
```

## Gentoo Tuning Analysis
```{python}
gentoo_cat = cat[cat["os"] == "Gentoo"]
px.box(gentoo_cat, x="host", y="mean_s", color="lto_enabled")
```

## Detailed Interpretation
Narrative on winners/losers, spread/variance, and tuning impacts.

## Caveats and Takeaways
Limitations, noisy categories, and practical conclusions.
```

- [ ] **Step 4: Run full render to verify all category pages**

Run: `quarto render docs/benchmarks-article`  
Expected: PASS and every category page has full deep-dive structure.

- [ ] **Step 5: Commit**

```bash
git add docs/benchmarks-article/categories/
git commit -m "docs: add detailed per-category benchmark deep-dives"
```

---

### Task 5: Validate repository checks and documentation consistency

**Files:**
- Modify (if needed): `docs/benchmarks-article/README.md`

- [ ] **Step 1: Add failing doc expectation**

Add/update README snippet that explains how to render full multi-page site:

```markdown
quarto render docs/benchmarks-article
quarto preview docs/benchmarks-article
```

- [ ] **Step 2: Run full validation**

Run:

```bash
uv run pytest tests/unit/ && \
uv run ruff check scripts/ tests/ && \
uv run ruff format --check scripts/ tests/ && \
uv run ansible-lint
```

Expected: PASS.

- [ ] **Step 3: Run final site render**

Run: `quarto render docs/benchmarks-article`  
Expected: PASS and no missing-page errors.

- [ ] **Step 4: Commit**

```bash
git add docs/benchmarks-article/README.md
git commit -m "docs: document multi-page deep-dive rendering workflow"
```

---

## Self-Review

- Spec coverage: methodology, data collection, all-category multi-page deep-dives, Gentoo tuning analysis, navigation, and verification are all mapped to tasks.
- Placeholder scan: no `TODO`/`TBD`; every task has concrete files, commands, and expected outcomes.
- Consistency check: helper naming (`build_category_summary`) and category-page section contract are consistent across tasks.
