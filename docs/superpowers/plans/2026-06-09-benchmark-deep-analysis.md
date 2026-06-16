# Benchmark Deep Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add methodology-first benchmark explanations, qualitative category write-ups, and metric-aware graphs to the existing Quarto article.

**Architecture:** Keep the current single Quarto article and replace the ad hoc category loop with a registry-driven renderer. A small Python helper module will provide category descriptions, metric kind (`time` vs `rate`), and sort direction so the article can render consistent narrative and graphs for every benchmark category without duplicating per-category logic in the notebook.

**Tech Stack:** Python, pandas, Plotly, Quarto, pytest.

---

## File Structure

- Create: `scripts/benchmark_category_reference.py`
  - Category registry and helper functions for titles, descriptions, metric kind, and sort direction.

- Modify: `docs/benchmarks-article/index.qmd`
  - Add the methodology/taxonomy section.
  - Replace the current generic category loop with registry-driven category deep dives.
  - Render the correct graph direction for `time` and `rate` categories.

- Create: `tests/unit/test_benchmark_category_reference.py`
  - Unit tests for category lookup, metric kind, and fallback behavior.

- Modify: `tests/unit/test_benchmarks_article_data.py`
  - Add one integration-style loader test if the article needs any new helper exposure from the data loader.

---

### Task 1: Add category reference helpers and unit tests

**Files:**
- Create: `scripts/benchmark_category_reference.py`
- Create: `tests/unit/test_benchmark_category_reference.py`

- [ ] **Step 1: Write the failing test**

```python
from benchmark_category_reference import get_category_reference


def test_compiler_rust_reference():
    ref = get_category_reference("compiler_rust")
    assert ref.title == "Compiler Rust"
    assert ref.metric_kind == "time"
    assert "Rust" in ref.description
    assert ref.sort_ascending is True


def test_memory_bandwidth_is_rate():
    ref = get_category_reference("memory_bandwidth")
    assert ref.title == "Memory Bandwidth"
    assert ref.metric_kind == "rate"
    assert ref.sort_ascending is False


def test_unknown_category_falls_back_to_time():
    ref = get_category_reference("new_future_category")
    assert ref.title == "New Future Category"
    assert ref.metric_kind == "time"
    assert ref.sort_ascending is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_benchmark_category_reference.py -v`
Expected: FAIL because `benchmark_category_reference.py` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
from dataclasses import dataclass
from typing import Literal

MetricKind = Literal["time", "rate"]


@dataclass(frozen=True)
class CategoryReference:
    title: str
    description: str
    metric_kind: MetricKind
    sort_ascending: bool


_COMPILER_SUFFIXES = {
    "c_compile": CategoryReference(
        title="Compiler C Compile",
        description="Measures how quickly the C toolchain compiles a small translation unit.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "c_runtime": CategoryReference(
        title="Compiler C Runtime",
        description="Measures how quickly the compiled C program runs.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "go": CategoryReference(
        title="Compiler Go",
        description="Measures how quickly Go builds the benchmark program.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "multifile": CategoryReference(
        title="Compiler Multifile",
        description="Measures how quickly the toolchain compiles a multi-file workload.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "rust": CategoryReference(
        title="Compiler Rust",
        description="Measures how quickly Rust builds the benchmark crate.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "sqlite": CategoryReference(
        title="Compiler SQLite",
        description="Measures how quickly the SQLite benchmark workload is compiled and exercised.",
        metric_kind="time",
        sort_ascending=True,
    ),
}


_CATEGORY_REFERENCES = {
    "compression": CategoryReference(
        title="Compression",
        description="Measures archive compression and decompression throughput under Hyperfine.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "crypto": CategoryReference(
        title="Crypto",
        description="Measures cryptographic workload runtime across representative algorithms.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "coreutils": CategoryReference(
        title="Coreutils",
        description="Measures common GNU coreutils commands under a repeatable workload.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "disk": CategoryReference(
        title="Disk",
        description="Measures sequential disk read and write performance on the benchmark work filesystem.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "ffmpeg": CategoryReference(
        title="FFmpeg",
        description="Measures video encode throughput using the FFmpeg benchmark workload.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "gimp": CategoryReference(
        title="GIMP",
        description="Measures an image-manipulation workload modeled on common GIMP operations.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "imagemagick": CategoryReference(
        title="ImageMagick",
        description="Measures batch image processing and resize work performed by ImageMagick.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "inkscape": CategoryReference(
        title="Inkscape",
        description="Measures vector-graphics rendering and export work in Inkscape.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "linker": CategoryReference(
        title="Linker",
        description="Measures linker throughput and relocation processing on the benchmark workload.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "memory_bandwidth": CategoryReference(
        title="Memory Bandwidth",
        description="Measures sequential memory bandwidth using the shared-memory benchmark.",
        metric_kind="rate",
        sort_ascending=False,
    ),
    "memory_latency": CategoryReference(
        title="Memory Latency",
        description="Measures pointer-chasing latency through the memory hierarchy.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "numeric": CategoryReference(
        title="Numeric",
        description="Measures numeric computation and math-heavy workloads.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "octave": CategoryReference(
        title="Octave",
        description="Measures Octave startup and scripted numerical processing work.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "opencv": CategoryReference(
        title="OpenCV",
        description="Measures computer-vision processing through OpenCV workloads.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "process": CategoryReference(
        title="Process",
        description="Measures process creation and shell execution overhead.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "python": CategoryReference(
        title="Python",
        description="Measures Python interpreter startup and execution overhead.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "sqlite": CategoryReference(
        title="SQLite",
        description="Measures SQLite write performance using the benchmark workload.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "startup": CategoryReference(
        title="Startup",
        description="Measures application startup latency across the benchmarked command.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "gentoo_build_times": CategoryReference(
        title="Gentoo Build Times",
        description="Measures Gentoo package build times across the workload set.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "boot_time": CategoryReference(
        title="Boot Time",
        description="Measures system boot phases and total boot duration.",
        metric_kind="time",
        sort_ascending=True,
    ),
    "bash": CategoryReference(
        title="Bash",
        description="Measures shell startup and execution overhead for Bash.",
        metric_kind="time",
        sort_ascending=True,
    ),
}


def get_category_reference(category: str) -> CategoryReference:
    if category.startswith("compiler_"):
        suffix = category.removeprefix("compiler_")
        return _COMPILER_SUFFIXES.get(
            suffix,
            CategoryReference(
                title=category.replace("_", " ").title(),
                description=f"Measures the {category} benchmark workload.",
                metric_kind="time",
                sort_ascending=True,
            ),
        )
    return _CATEGORY_REFERENCES.get(
        category,
        CategoryReference(
            title=category.replace("_", " ").title(),
            description=f"Measures the {category} benchmark workload.",
            metric_kind="time",
            sort_ascending=True,
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_benchmark_category_reference.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/benchmark_category_reference.py tests/unit/test_benchmark_category_reference.py
git commit -m "feat: add benchmark category reference metadata"
```

---

### Task 2: Rewrite the article deep-dive loop around the category registry

**Files:**
- Modify: `docs/benchmarks-article/index.qmd`

- [ ] **Step 1: Write the failing render check**

Run:

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager && uv run quarto render docs/benchmarks-article/index.qmd
```

Expected: the article still renders the old generic category loop and does not yet use the category registry.

- [ ] **Step 2: Write the minimal implementation**

Replace the current `for category in category_names:` block with a registry-driven renderer:

```python
from benchmark_category_reference import get_category_reference


def metric_value_series(category_frame, metric_kind):
    if metric_kind == "rate":
        return category_frame["mean_s"]
    return category_frame["mean_s"]


for category in category_names:
    ref = get_category_reference(category)
    cat_df = df[df["category"] == category].copy()
    if cat_df.empty:
        continue

    cat_df["os_display"] = cat_df.apply(
        lambda row: row["distro_label"] if str(row.get("distro_label", "")).strip() else row["os"],
        axis=1,
    )
    cat_df["metric_value"] = metric_value_series(cat_df, ref.metric_kind)

    display(Markdown(f"### {ref.title}"))
    display(Markdown(ref.description))
    display(Markdown(f"**Metric direction:** {'higher is better' if ref.metric_kind == 'rate' else 'lower is better'}"))

    os_summary = (
        cat_df.groupby("os_display", as_index=False)["metric_value"]
        .median()
        .rename(columns={"metric_value": "median_value"})
        .sort_values("median_value", ascending=ref.sort_ascending)
    )

    fig_os = px.bar(
        os_summary,
        x="os_display",
        y="median_value",
        title=f"{ref.title}: Median by operating system",
        labels={"os_display": "Operating system", "median_value": "Median value"},
    )
    fig_os.update_layout(xaxis_tickangle=-30)
    fig_os

    gentoo_cat = cat_df[cat_df["os"] == "Gentoo"].copy()
    if not gentoo_cat.empty:
        fig_gentoo = px.box(
            gentoo_cat,
            x="host",
            y="metric_value",
            color="distro_label",
            title=f"{ref.title}: Gentoo host distribution",
            labels={"host": "Host", "metric_value": "Metric value"},
            points="all",
        )
        fig_gentoo.update_layout(xaxis_tickangle=-30)
        fig_gentoo
```

Then keep the existing outlier note and qualitative interpretation block, but feed it from `ref.description` and the chosen metric direction.

- [ ] **Step 3: Run the render check again**

Run:

```bash
cd /home/pk/Devel/Ansible/local.gentoomanager && uv run quarto render docs/benchmarks-article/index.qmd
```

Expected: the article renders with the methodology section plus registry-driven category sections and graphs.

- [ ] **Step 4: Commit**

```bash
git add docs/benchmarks-article/index.qmd
git commit -m "docs: make benchmark deep dives registry driven"
```

---

### Task 3: Verify article rendering and keep the benchmark math intact

**Files:**
- Modify: `docs/benchmarks-article/README.md` (only if render instructions need to mention the new category registry)

- [ ] **Step 1: Write the failing validation check**

Add or update a render note if needed:

```markdown
quarto render docs/benchmarks-article/index.qmd
```

- [ ] **Step 2: Run the validation commands**

Run:

```bash
uv run pytest tests/unit/test_benchmark_category_reference.py -q && \
uv run pytest tests/unit/test_benchmarks_article_data.py -q && \
uv run quarto render docs/benchmarks-article/index.qmd
```

Expected: PASS.

- [ ] **Step 3: Confirm the article keeps the existing summary math**

Verify the rendered article still contains the existing benchmark summary, host summary, and tuning comparison blocks, and that the new category sections do not replace those calculations.

- [ ] **Step 4: Commit**

```bash
git add docs/benchmarks-article/README.md
git commit -m "docs: document benchmark deep analysis workflow"
```

---

## Self-Review

- Spec coverage: methodology, registry-driven category descriptions, metric-aware graphing, and qualitative analysis are each covered by a task.
- Placeholder scan: no TBD/TODO/fill-in language remains.
- Type consistency: the `CategoryReference` dataclass and `get_category_reference()` helper are used consistently across the plan, and the article loop consumes `metric_kind` and `sort_ascending` exactly as defined.
