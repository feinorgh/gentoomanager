"""Benchmark category metadata catalog for article presentation.

Each entry in the catalog describes what a benchmark category measures,
how to interpret results, and drives chart labels and sort direction.
All categories currently store timing data (hyperfine ``mean_s``), so
``metric_kind`` is ``"time"`` (lower is better) for every entry. The field
exists for forward-compatibility with future rate-based (higher is better)
categories.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MetricKind = Literal["time", "rate"]


@dataclass(frozen=True)
class CategoryMeta:
    """Presentation metadata for one benchmark category."""

    title: str
    description: str
    metric_kind: MetricKind
    unit_label: str
    y_axis_label: str
    analysis_hint: str

    @property
    def lower_is_better(self) -> bool:
        """True for time-based metrics, False for rate/throughput metrics."""
        return self.metric_kind == "time"

    @property
    def direction_note(self) -> str:
        """Short phrase stating the optimal direction for chart readers."""
        return "lower is better" if self.lower_is_better else "higher is better"

    @property
    def winner_label(self) -> str:
        """Label used to call out the best-performing OS or configuration."""
        return "fastest" if self.lower_is_better else "highest throughput"

    @property
    def sort_ascending(self) -> bool:
        """True means ascending sort shows the best (lowest) value first in charts."""
        return self.lower_is_better


_CATALOG: dict[str, CategoryMeta] = {
    "compression": CategoryMeta(
        title="Compression",
        description=(
            "Measures wall-clock time to compress and decompress a fixed test blob with gzip, "
            "bzip2, xz, zstd, and lz4. These workloads are CPU-bound integer algorithms; "
            "performance reflects branch-prediction quality, memory bandwidth, and SIMD "
            "availability. Compression speed has direct practical impact on Gentoo binary-package "
            "creation (e.g., with `BINPKG_COMPRESS=zstd`) and source-tarball handling."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Runtime (seconds)",
        analysis_hint=(
            "lz4 is typically fastest; xz is slowest but achieves the best compression ratio. "
            "LTO and `-march=native` can enable SIMD paths in zstd and gzip, reducing runtime "
            "by 5–15 %."
        ),
    ),
    "crypto": CategoryMeta(
        title="Cryptography",
        description=(
            "Tests symmetric encryption (AES-128/256-CBC/GCM), cryptographic hash functions "
            "(SHA-256, SHA-512, BLAKE2b), and asymmetric operations (RSA, ECDSA) via "
            "`openssl speed`, plus GPG sign/verify round-trips. Although OpenSSL reports "
            "internal throughput in MB/s, what gets stored here is the wall-clock time to "
            "complete a fixed-volume run — so **lower runtime is still better**. Results are "
            "highly sensitive to AES-NI, SHA-NI, and AVX2/AVX-512 hardware acceleration."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Runtime (seconds)",
        analysis_hint=(
            "AES-NI and SHA-NI explain the largest inter-host differences. `-march=native` "
            "unlocks AVX2 vectorisation paths in OpenSSL; missing or mismatched `CPU_FLAGS_X86` "
            "is the most common cause of underperformance here."
        ),
    ),
    "memory": CategoryMeta(
        title="Memory Bandwidth & Latency",
        description=(
            "Two complementary workloads: (1) sequential bandwidth via large block transfers "
            "through `/dev/shm` (tmpfs), reflecting DRAM transfer rate; (2) random-access "
            "latency via a compiled pointer-chasing program that defeats hardware prefetchers. "
            "These capture the memory-subsystem hierarchy — L1/L2/L3 cache sizes, DRAM speed, "
            "and NUMA topology — which compute-bound benchmarks cannot expose. Results reflect "
            "VM configuration more than compiler flags."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Runtime (seconds)",
        analysis_hint=(
            "Sequential bandwidth is primarily a DRAM and VM-memory-allocation signal. "
            "Latency results show step changes at cache boundaries; a jump between hosts "
            "often indicates different DRAM speed tiers or NUMA pinning differences."
        ),
    ),
    "disk": CategoryMeta(
        title="Disk I/O",
        description=(
            "Sequential read/write throughput on the benchmark work-directory filesystem, "
            "measured with `dd`-style block transfers. Results depend heavily on the VM storage "
            "backend (virtio-blk, NVMe passthrough, NFS) and filesystem type (btrfs CoW vs "
            "ext4). They are intentionally not comparable across runs if the storage backend "
            "changes. This benchmark exposes the I/O ceiling for workloads such as package "
            "building, source extraction, and log processing."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Runtime (seconds)",
        analysis_hint=(
            "Large spreads usually reflect storage-backend configuration rather than compiler "
            "flags. btrfs copy-on-write can add write overhead compared to ext4; `nodatacow` "
            "mount options reduce this for build directories."
        ),
    ),
    "process": CategoryMeta(
        title="Process Creation",
        description=(
            "Measures fork/exec/waitpid round-trip latency and shell spawn rate. Fork+exec is "
            "the fundamental bottleneck in Gentoo package builds, where thousands of short-lived "
            "processes (configure scripts, `ar`, `ranlib`, `strip`, `make`) are spawned "
            "sequentially. A 10 % improvement here translates directly into a 10 % shorter "
            "total build time for large packages such as LLVM or GCC itself."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Runtime (seconds)",
        analysis_hint=(
            "Kernel scheduler tuning and the libc `fork` implementation both contribute. "
            "LTO on glibc or musl can marginally reduce fork overhead; the bigger lever is "
            "kernel version and scheduler policy (CFS vs EEVDF)."
        ),
    ),
    "linker": CategoryMeta(
        title="Linker Performance",
        description=(
            "Measures wall-clock link time for a synthetic multi-object C project with GNU ld "
            "(BFD), GNU gold, and LLVM lld where available. Linking is the serial bottleneck "
            "for large C++ packages (LLVM, Chromium, Firefox); reducing link time has a direct "
            "impact on developer iteration speed and total build wall-clock time. Results vary "
            "with memory bandwidth (linkers are I/O-bound for large relocatable object sets) "
            "and LTO link-time code-generation overhead."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Link time (seconds)",
        analysis_hint=(
            "lld is almost always faster than BFD for large projects. LTO increases link time "
            "while reducing runtime; evaluate the cost/benefit per package rather than globally. "
            "mold is not yet included but would be the fastest option for incremental links."
        ),
    ),
    "ffmpeg": CategoryMeta(
        title="FFmpeg Encode/Decode",
        description=(
            "Runs discovered FFmpeg encode and decode pipelines over short synthetic clips, "
            "covering software video codecs (H.264, H.265, VP9, AV1) and audio codecs "
            "(AAC, Opus). Although FFmpeg reports internal throughput in fps, the stored "
            "metric is wall-clock time to transcode a fixed-length clip — so **lower is "
            "better**. These workloads are highly parallelised and benefit from AVX2/AVX-512 "
            "instruction sets, thread pool sizing, and libx265/libaom build quality."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Transcode time (seconds)",
        analysis_hint=(
            "`CPU_FLAGS_X86` and AVX-512 availability drive most of the inter-host spread. "
            "Software AV1 encoding (libaom) is especially sensitive to SIMD and thread count; "
            "expect it to be the slowest codec by a wide margin."
        ),
    ),
    "imagemagick": CategoryMeta(
        title="ImageMagick Processing",
        description=(
            "Tests ImageMagick image processing: resize with various filter qualities, "
            "convolution/blur effects, and format encode/decode round-trips (JPEG, WebP, PNG). "
            "Results are sensitive to AVX2/AVX-512 SIMD extensions, the build quality of "
            "libjpeg-turbo and libwebp, and whether OpenMP parallelism is enabled at compile "
            "time. This provides a strong `compiler-flag` and `CPU_FLAGS_X86` signal for "
            "multimedia workloads."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Processing time (seconds)",
        analysis_hint=(
            "libjpeg-turbo (SIMD-accelerated JPEG) gives the largest single uplift. Graphite "
            "loop transformations can help with convolution kernels. Check that "
            "`CPU_FLAGS_X86=avx2` is set before assuming an architecture ceiling has been hit."
        ),
    ),
    "opencv": CategoryMeta(
        title="OpenCV Processing",
        description=(
            "Runs OpenCV image-processing pipelines through the Python bindings: color-space "
            "conversion, Gaussian blur, Canny edge detection, and JPEG decode/encode. OpenCV "
            "uses a Hardware Acceleration Layer (HAL) that dispatches to SSE/AVX code paths "
            "at runtime. Results reflect the combination of Python interpreter overhead and "
            "OpenCV's SIMD paths; the interpreter adds a roughly constant baseline cost."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Processing time (seconds)",
        analysis_hint=(
            "Differences at the slow end often reflect cache-miss penalties during large-image "
            "convolution passes. PGO on CPython reduces the interpreter overhead component and "
            "narrows the gap between configurations."
        ),
    ),
    "gimp": CategoryMeta(
        title="GIMP Cold-Start",
        description=(
            "Measures wall-clock time for GIMP to cold-start, initialise its plugin and font "
            "subsystems, and exit cleanly (`gimp -i -n --no-data --no-fonts --quit`). This is "
            "a proxy for application launch latency — dominated by dynamic-linker resolution, "
            "glib/gtk initialisation, and plugin discovery. It is less sensitive to CPU "
            "optimisation than to filesystem (page-cache state) and dynamic-linker "
            "configuration (`ld.so` cache freshness)."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Cold-start time (seconds)",
        analysis_hint=(
            "The first run is almost always an outlier due to cold page cache; hyperfine "
            "discards it as a warm-up. LTO can slightly reduce startup time by eliminating "
            "dead code and improving instruction-cache locality in the GIMP binary."
        ),
    ),
    "inkscape": CategoryMeta(
        title="Inkscape SVG Rendering",
        description=(
            "Renders a complex synthetic SVG (300 Bézier paths with gradients and filter "
            "effects, 80 grouped rectangles, 60 text elements) at multiple DPI settings and "
            "exports as PDF. This exercises Inkscape's 2D rendering engine, Cairo, and the "
            "SVG/XML parser. Results are sensitive to Cairo's SIMD compositing paths and to "
            "the GTK/Pango stack. Font loading is excluded by design to keep the benchmark "
            "CPU-bound rather than I/O-bound."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Render time (seconds)",
        analysis_hint=(
            "Cairo uses SSE2/AVX2 compositing internally; enabling `CPU_FLAGS_X86=avx2` in "
            "the Cairo build improves throughput for complex filter effects. The SVG fixture "
            "was designed to stress-test filter stacking, not just path rasterisation."
        ),
    ),
    "startup": CategoryMeta(
        title="Application Startup",
        description=(
            "Times cold-start and warm-start latency for available GUI applications (Firefox, "
            "GIMP, Inkscape) in a single pass, enabling direct cross-application comparisons. "
            "Unlike the dedicated GIMP and Inkscape categories, this section captures each "
            "application with identical methodology. Results reflect dynamic-linker speed, "
            "page-cache state, and each application's own initialisation overhead rather than "
            "their computational performance."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Startup time (seconds)",
        analysis_hint=(
            "Differences across distributions often reflect prelink status and `ld.so` cache "
            "recency rather than CPU optimisation. Warm-start times converge faster than "
            "cold-start times across configurations."
        ),
    ),
    "bash": CategoryMeta(
        title="Bash Shell Performance",
        description=(
            "Profiles the bash interpreter across four micro-benchmarks relevant to build-system "
            "workloads: raw binary start/exit overhead (no rc files), integer arithmetic via "
            "`(( ))` in tight loops, string concatenation with `+=`, and global pattern "
            "substitution `${s//x/y}`. Build systems for Autoconf-based projects and Gentoo "
            "ebuilds generate thousands of bash invocations; small per-invocation costs compound "
            "across a full rebuild."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Runtime (seconds)",
        analysis_hint=(
            "Startup overhead dominates short scripts. PGO on bash measurably reduces startup "
            "latency by improving branch prediction for the interpreter's hot dispatch paths. "
            "Arithmetic and string-substitution results are less sensitive to compiler flags "
            "than the raw startup cost."
        ),
    ),
    "boot_time": CategoryMeta(
        title="System Boot Time",
        description=(
            "Collects system boot timing via `systemd-analyze` (accurate phase breakdown with "
            "per-service blame) or dmesg timestamp parsing for non-systemd hosts. Reports "
            "firmware, loader, kernel, and userspace phase durations. Boot time reflects the "
            "combined cost of kernel init, udev settlement, and service startup ordering. It is "
            "primarily a system configuration signal rather than a compiler optimisation signal."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Boot time (seconds)",
        analysis_hint=(
            "Large spreads usually reflect service-configuration differences rather than "
            "compiler optimisation. systemd socket activation and service-dependency "
            "parallelism have a larger impact on boot time than any `CFLAGS` choice."
        ),
    ),
    "gentoo_build_times": CategoryMeta(
        title="Gentoo Package Build Times",
        description=(
            "Extracts actual package build durations from `emerge.log` via `qlop`, focusing on "
            "packages whose longest recorded build exceeds 5 minutes. This is the most direct "
            "measurement of Gentoo-specific compilation overhead and the cost of enabling "
            "features such as LTO or PGO. It captures the real-world trade-off: build-time "
            "investment vs runtime performance gain. Kernel version, compiler version, and "
            "enabled USE flags all influence these results."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Build time (seconds)",
        analysis_hint=(
            "LTO and PGO add significant build-time cost for large packages such as Firefox "
            "or LibreOffice. Compare these build-time costs against runtime benchmark "
            "improvements to assess whether a tuning profile provides a worthwhile return."
        ),
    ),
    "numeric": CategoryMeta(
        title="Numeric / Floating-Point",
        description=(
            "Runs compiled C implementations of classic numeric benchmarks (n-body simulation, "
            "Mandelbrot set rendering, spectral norm) alongside NumPy workloads (matrix "
            "multiplication, FFT, sort). These stress floating-point vectorisation (FMA, "
            "AVX2, AVX-512), BLAS library selection in NumPy, and compiler auto-vectorisation. "
            "They provide a strong compiler-flag and `CPU_FLAGS_X86` signal for scientific "
            "and data-processing workloads."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Runtime (seconds)",
        analysis_hint=(
            "AVX-512 FMA gives the largest uplift for n-body and spectral-norm. OpenBLAS vs "
            "reference BLAS dominates matrix-multiplication results independently of CFLAGS; "
            "verify `sci-libs/blas-reference` is not masking a faster BLAS."
        ),
    ),
    "octave": CategoryMeta(
        title="GNU Octave Numerical",
        description=(
            "Runs GNU Octave matrix and numerical-computation benchmarks: matrix decomposition "
            "(LU, QR, SVD), elementwise operations, and linear system solving. Octave links "
            "against BLAS/LAPACK and benefits from the same SIMD paths as the C numeric "
            "benchmarks. Results reflect BLAS library selection, Octave JIT status, and "
            "compiler flags used for the Octave and BLAS builds."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Runtime (seconds)",
        analysis_hint=(
            "BLAS library selection (OpenBLAS vs reference BLAS) dominates; LTO on Octave "
            "itself has minor effect compared to the BLAS choice. Enable `USE=openblas` "
            "before optimising Octave CFLAGS."
        ),
    ),
    "compiler": CategoryMeta(
        title="Compiler Speed",
        description=(
            "Measures wall-clock time to compile a synthetic C project with gcc and clang "
            "(plus rustc and go where available). Compiler speed is itself a meta-benchmark: "
            "a faster compiler host means shorter build times across all packages. Results "
            "depend on compiler version, optimisation level of the compiler binary itself, "
            "and available parallelism. PGO-compiled GCC noticeably reduces compilation "
            "latency for its own invocations."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Compilation time (seconds)",
        analysis_hint=(
            "A PGO-built GCC compiles code measurably faster. Comparing gcc vs clang latency "
            "here also informs which compiler to use for fast interactive iteration. Expect "
            "the largest differences between LTO+PGO configurations and the baseline."
        ),
    ),
    "python": CategoryMeta(
        title="Python Performance",
        description=(
            "Benchmarks the CPython interpreter with workloads representative of build-system "
            "and scripting use cases: JSON encode/decode, regular-expression matching, list "
            "comprehensions, and string formatting. Results reflect the CPython version, PGO "
            "status of the CPython binary, and the presence of optional accelerators. On "
            "Gentoo, PGO is available for CPython and has measurable effect on interpreter "
            "dispatch throughput."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Runtime (seconds)",
        analysis_hint=(
            "PGO on CPython measurably reduces interpreter dispatch overhead. Python version "
            "differences (3.11 vs 3.12) also contribute independently of system-level "
            "optimisation; record the Python version from `tool_versions` when comparing."
        ),
    ),
    "sqlite": CategoryMeta(
        title="SQLite Throughput",
        description=(
            "Exercises the SQLite library with a one-million-row bulk INSERT, indexed SELECT "
            "queries, full-table scan, and ORDER BY sorting. Tests B-tree manipulation, the "
            "query planner, and branch-prediction-sensitive code paths in SQLite. SQLite is "
            "embedded in many Gentoo tools (portage, qlop) and in web browsers; its "
            "performance is a strong PGO and branch-optimisation signal. All workloads run "
            "in-process via Python's `sqlite3` module."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Runtime (seconds)",
        analysis_hint=(
            "PGO shows consistent improvement for SQLite because its B-tree traversal has "
            "highly predictable hot paths that profile-guided optimisation captures well. "
            "This is one of the clearest PGO signals in the entire benchmark suite."
        ),
    ),
    "coreutils": CategoryMeta(
        title="Coreutils & Dev Tools",
        description=(
            "Benchmarks standard Unix utilities that frequently appear in build pipelines: "
            "`sort` on a large text file, `grep` with regex search, `find`, and similar. "
            "These represent the overhead of build-system scaffolding rather than application "
            "logic — faster coreutils mean faster `configure` scripts, Makefile evaluation, "
            "and package-manager operations. Absolute differences are small but multiply "
            "across the thousands of coreutils invocations in a full system rebuild."
        ),
        metric_kind="time",
        unit_label="seconds",
        y_axis_label="Runtime (seconds)",
        analysis_hint=(
            "GNU `sort` and `grep` benefit from SIMD-accelerated string comparison paths. "
            "Differences are small in absolute terms but compound across full-rebuild workloads. "
            "Watch for unusually slow `find` results, which often indicate inode-table pressure "
            "from CoW filesystems."
        ),
    ),
}

_DEFAULT_META = CategoryMeta(
    title="",  # overridden by get_category_meta
    description=(
        "This category has no dedicated catalog entry. Results are rendered as a "
        "time-based (lower is better) benchmark using raw `mean_s` timing data. "
        "Refer to the benchmark task source under `roles/run_benchmarks/tasks/` "
        "for workload details."
    ),
    metric_kind="time",
    unit_label="seconds",
    y_axis_label="Runtime (seconds)",
    analysis_hint="Lower is better (default time-based interpretation).",
)


def get_category_meta(category: str) -> CategoryMeta:
    """Return CategoryMeta for a category name, or a safe default if not in catalog."""
    if category in _CATALOG:
        return _CATALOG[category]
    title = category.replace("_", " ").title()
    return CategoryMeta(
        title=title,
        description=_DEFAULT_META.description,
        metric_kind=_DEFAULT_META.metric_kind,
        unit_label=_DEFAULT_META.unit_label,
        y_axis_label=_DEFAULT_META.y_axis_label,
        analysis_hint=_DEFAULT_META.analysis_hint,
    )


def catalog_categories() -> list[str]:
    """Return all category names present in the catalog."""
    return list(_CATALOG.keys())
