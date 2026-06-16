# CFLAGS Deep-Dive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Gentoo-focused CFLAGS deep-dive section to the benchmark article, including `-march=native` vs generic analysis and key optimization-flag effects.

**Architecture:** Implement a dedicated parser/helper module to normalize CFLAGS dimensions (`march_class`, `opt_level`, `lto_mode`, `pgo_mode`, `graphite_mode`) from existing metadata rows, then consume those derived columns in `index.qmd` for aggregate and per-category visual analysis. Keep parsing logic in Python helper code and keep Quarto focused on presentation and interpretation.

**Tech Stack:** Python 3.13+, pandas, numpy, plotly, Quarto, pytest, ruff.

---

## File Structure

- Create: `scripts/benchmarks_cflags_analysis.py`
  - Single responsibility: parse and enrich Gentoo rows with normalized CFLAGS dimensions.
- Create: `tests/unit/test_benchmarks_cflags_analysis.py`
  - Single responsibility: parser/enrichment behavior tests.
- Modify: `docs/benchmarks-article/index.qmd`
  - Single responsibility: render CFLAGS deep-dive tables/charts/interpretation from enriched rows.
- Create: `changelogs/fragments/cflags-deep-dive.yml`
  - Single responsibility: user-visible change note.

### Task 1: Build CFLAGS parser helper with TDD

**Files:**
- Create: `scripts/benchmarks_cflags_analysis.py`
- Test: `tests/unit/test_benchmarks_cflags_analysis.py`

- [ ] **Step 1: Write failing parser tests**

```python
def test_classify_march_native_like():
    assert classify_march_class("-O2 -pipe -march=native") == "native_like"

def test_classify_march_generic_like():
    assert classify_march_class("-O2 -pipe -march=x86-64-v3") == "generic_like"

def test_parse_opt_level_conflict():
    assert parse_opt_level("-O2 -O3") == "other"

def test_parse_lto_modes():
    assert parse_lto_mode("-O2 -flto") == "on"
    assert parse_lto_mode("-O2 -flto=auto") == "auto"
    assert parse_lto_mode("-O2 -flto=thin") == "thin"

def test_parse_pgo_modes():
    assert parse_pgo_mode("-O2 -fprofile-generate") == "generate"
    assert parse_pgo_mode("-O2 -fprofile-use") == "use"
    assert parse_pgo_mode("-O2 -fprofile-generate -fprofile-use") == "both_or_other"
```

- [ ] **Step 2: Run tests to verify failure**

Run:
```bash
uv run pytest -q tests/unit/test_benchmarks_cflags_analysis.py
```

Expected: FAIL with import/function-not-found errors.

- [ ] **Step 3: Implement minimal parser module**

```python
def normalize_flag_text(common_flags: str, cflags: str, ldflags: str) -> str:
    return " ".join([common_flags or "", cflags or "", ldflags or ""]).lower()

def classify_march_class(flag_text: str) -> str:
    if "-march=native" in flag_text or "-mtune=native" in flag_text:
        return "native_like"
    if "-march=x86-64" in flag_text or "-march=x86-64-v" in flag_text:
        return "generic_like"
    return "unknown"

def enrich_gentoo_cflags_dimensions(df: pd.DataFrame) -> pd.DataFrame:
    enriched = df.copy()
    # add: march_class, opt_level, lto_mode, pgo_mode, graphite_mode
    return enriched
```

- [ ] **Step 4: Expand tests for enrichment behavior**

```python
def test_enrich_gentoo_cflags_dimensions_adds_expected_columns(sample_df):
    enriched = enrich_gentoo_cflags_dimensions(sample_df)
    assert {"march_class", "opt_level", "lto_mode", "pgo_mode", "graphite_mode"} <= set(enriched.columns)

def test_enrich_only_affects_gentoo_rows(sample_df):
    enriched = enrich_gentoo_cflags_dimensions(sample_df)
    assert enriched.loc[enriched["os"] != "Gentoo", "march_class"].eq("unknown").all()
```

- [ ] **Step 5: Run tests to verify pass**

Run:
```bash
uv run pytest -q tests/unit/test_benchmarks_cflags_analysis.py
```

Expected: PASS.

- [ ] **Step 6: Commit parser + tests**

```bash
git add scripts/benchmarks_cflags_analysis.py tests/unit/test_benchmarks_cflags_analysis.py
git commit -m "feat: add Gentoo CFLAGS analysis parser"
```

### Task 2: Add CFLAGS deep-dive article section

**Files:**
- Modify: `docs/benchmarks-article/index.qmd`
- Create/Reuse import: `scripts/benchmarks_cflags_analysis.py`

- [ ] **Step 1: Write failing content expectations test**

```python
def test_article_includes_cflags_deep_dive_heading():
    qmd = Path("docs/benchmarks-article/index.qmd").read_text(encoding="utf-8")
    assert "## Gentoo CFLAGS Deep-Dive" in qmd
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
uv run pytest -q tests/unit/test_benchmarks_article_data.py::test_benchmarks_article_data_has_no_shebang
```

Expected: PASS (baseline sanity only).  
Then run quick grep check:
```bash
rg -n "## Gentoo CFLAGS Deep-Dive" docs/benchmarks-article/index.qmd
```

Expected: no match before implementation.

- [ ] **Step 3: Implement article integration**

Add to `index.qmd`:

```python
from benchmarks_cflags_analysis import enrich_gentoo_cflags_dimensions
...
gentoo_df = df[df["os"] == "Gentoo"].copy()
gentoo_df = enrich_gentoo_cflags_dimensions(gentoo_df)
```

Add section scaffold:

```markdown
## Gentoo CFLAGS Deep-Dive
```

Add outputs:
1. Coverage table by host and parsed dimensions.
2. Aggregate effect charts (all-sample medians by `march_class`, `opt_level`, `lto_mode`, `pgo_mode`, `graphite_mode`).
3. Per-category effect heatmap/grouped bars.
4. Interpretation callout with confounders and stability caveats.

- [ ] **Step 4: Run formatting/lint checks for changed Python files**

Run:
```bash
uv run ruff check scripts/ tests/
uv run ruff format --check scripts/ tests/
```

Expected: PASS.

- [ ] **Step 5: Render article to verify execution**

Run:
```bash
uv run quarto render docs/benchmarks-article/index.qmd
```

Expected: render succeeds and includes “Gentoo CFLAGS Deep-Dive”.

- [ ] **Step 6: Commit article integration**

```bash
git add docs/benchmarks-article/index.qmd
git commit -m "feat: add Gentoo CFLAGS deep-dive section"
```

### Task 3: Final verification, changelog, and polish

**Files:**
- Create: `changelogs/fragments/cflags-deep-dive.yml`
- Test: `tests/unit/test_benchmarks_cflags_analysis.py`
- Modify (if needed): `docs/benchmarks-article/index.qmd`

- [ ] **Step 1: Add changelog fragment**

```yaml
minor_changes:
  - "docs/benchmarks-article: added a Gentoo CFLAGS deep-dive covering -march=native vs generic, optimization-level groups, and LTO/PGO/Graphite effect comparisons."
  - "scripts/benchmarks_cflags_analysis: added normalized CFLAGS-dimension parsing for article-side analysis."
```

- [ ] **Step 2: Run targeted tests**

Run:
```bash
uv run pytest -q tests/unit/test_benchmarks_cflags_analysis.py tests/unit/test_benchmarks_article_data.py
```

Expected: PASS.

- [ ] **Step 3: Run repository verification commands relevant to this change**

Run:
```bash
uv run pytest tests/unit/
uv run ruff check scripts/ tests/
uv run ruff format --check scripts/ tests/
```

Expected: PASS.

- [ ] **Step 4: Final commit**

```bash
git add changelogs/fragments/cflags-deep-dive.yml
git commit -m "docs: document CFLAGS deep-dive analysis"
```

## Spec Coverage Check

- Parser/helper module: covered by Task 1.
- Data model dimensions (`march_class`, `opt_level`, `lto_mode`, `pgo_mode`, `graphite_mode`): covered by Task 1 tests and implementation.
- Aggregate and per-category article outputs: covered by Task 2.
- Error/degradation behavior and confounder caveats: covered by Task 2 interpretation/callouts.
- Changelog and verification: covered by Task 3.

## Placeholder / Consistency Check

- No placeholders (`TODO/TBD`) remain.
- Function names are consistent across tasks (`enrich_gentoo_cflags_dimensions`, `classify_march_class`, `parse_opt_level`, `parse_lto_mode`, `parse_pgo_mode`).
- Scope remains article-side analysis only, matching approved spec.
