#!/usr/bin/env python3
"""Generate Markdown and HTML benchmark reports from hyperfine JSON results.

Usage::

    python3 scripts/generate_benchmark_report.py benchmarks/
    python3 scripts/generate_benchmark_report.py benchmarks/ --anonymize

Reads ``benchmarks/results/<host>/*.json`` and produces:
- ``benchmarks/report.md``  — Markdown tables
- ``benchmarks/report.html`` — Interactive HTML with Chart.js charts
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Chart.js colors — one per host, cycling if >16 hosts
CHART_COLORS = [
    "#4dc9f6",
    "#f67019",
    "#f53794",
    "#537bc4",
    "#acc236",
    "#166a8f",
    "#00a950",
    "#58595b",
    "#8549ba",
    "#e6194b",
    "#3cb44b",
    "#ffe119",
    "#4363d8",
    "#f58231",
    "#911eb4",
    "#42d4f4",
]

# Maps benchmark category prefixes to the metadata version key for that category's primary tool.
# Used to add a per-host "Tool version" row in comparison tables.
_CATEGORY_TOOL_VERSION: dict[str, str | None] = {
    "compiler": None,  # multiple compilers; version encoded in command label
    "startup": None,  # many tools
    "python": None,  # multiple Python versions; version encoded in command label
    "crypto": "openssl",
    "ffmpeg": "ffmpeg",
    "imagemagick": "imagemagick",
    "compression": "7z",
    "linker": "lld",
    "bash": "bash",
    "sqlite": "sqlite3",
    "numeric": "python",  # numpy/python benchmarks
    "opencv": "python",
    "gimp": "gimp",
    "inkscape": "inkscape",
}

CATEGORY_TITLES = {
    "compression": "Compression",
    "crypto_symmetric": "Cryptography — Symmetric Ciphers",
    "crypto_hash": "Cryptography — Digests (OpenSSL)",
    "crypto_hash_coreutils": "Cryptography — Digests (Coreutils)",
    "crypto_openssl_speed": "OpenSSL Speed — Symmetric & AEAD Throughput",
    "crypto_asymmetric": "Cryptography — Asymmetric / Public Key (OpenSSL)",
    "crypto_hmac": "Cryptography — HMAC",
    "crypto_kdf": "Cryptography — Key Derivation",
    "crypto_gpg": "GPG Sign / Verify",
    "crypto_aes": "Cryptography — AES (legacy)",
    "crypto_ssh_sign": "Cryptography — SSH Signing (OpenSSH)",
    "crypto_botan": "Cryptography — Asymmetric / Public Key (Botan)",
    "compiler_c_compile": "C Compilation Speed",
    "compiler_c_runtime": "C Runtime Performance",
    "compiler_rust": "Rust Compilation Speed",
    "compiler_go": "Go Compilation Speed",
    "python": "Python Performance",
    "ffmpeg_video_encode": "FFmpeg Video Encoding",
    "ffmpeg_video_decode": "FFmpeg Video Decoding",
    "ffmpeg_audio_encode": "FFmpeg Audio Encoding",
    "ffmpeg_audio_decode": "FFmpeg Audio Decoding",
    "imagemagick_resize": "ImageMagick — Resize (filter comparison)",
    "imagemagick_effects": "ImageMagick — Effects (blur, sharpen, transform)",
    "imagemagick_encode": "ImageMagick — Format Encoding",
    "imagemagick_decode": "ImageMagick — Format Decoding",
    "coreutils": "Coreutils & Shell Tools",
    "git": "Git Operations",
    "diff": "Diff / Comm",
    "opencv": "OpenCV Image Processing",
    "startup": "Application Startup",
    "numeric_compiled": "Numeric — Compiled C (N-body, Mandelbrot, Spectral Norm)",
    "numeric_numpy": "Numeric — NumPy (matmul, FFT, sort)",
    "sqlite_write": "SQLite — Write (bulk INSERT, UPDATE)",
    "sqlite_read": "SQLite — Read (indexed SELECT, full scan, ORDER BY)",
    "memory_bandwidth": "Memory — Sequential Bandwidth (write/read to tmpfs)",
    "memory_latency": "Memory — Random Access Latency (pointer chasing)",
    "process": "Process Creation (fork/exec rate)",
    "disk": "Disk I/O — Sequential (256 MiB write/read)",
    "linker": "Linker Performance (bfd / lld / gold)",
    "bash": "Bash Shell Performance",
}

# Categories not run on Windows (complement of run_benchmarks_windows_categories)
_WINDOWS_EXCLUDED: frozenset[str] = frozenset(
    {
        "boot_time",
        "bash",
        "memory",
        "disk",
        "opencv",
        "gimp",
        "inkscape",
        "gentoo_build_times",
    }
)

# Mapping from tool name → category names it affects
_TOOL_CATEGORIES: dict[str, list[str]] = {
    "clang": ["compiler"],
    "rustc": ["compiler"],
    "go": ["compiler"],
    "ffmpeg": ["ffmpeg"],
    "imagemagick": ["imagemagick"],
    "7zip": ["compression"],
}

# Mapping from sub-benchmark name patterns → required tool
_BENCH_TOOL_MAP: list[tuple[str, str]] = [
    ("rust", "rustc"),
    ("cargo", "rustc"),
    ("-go", "go"),
    ("go-", "go"),
    ("go_", "go"),
    ("clang", "clang"),
    ("ffmpeg", "ffmpeg"),
    ("magick", "imagemagick"),
]

# Greek mythology names for host anonymization (deterministic order)
_GREEK_NAMES = [
    "Zeus",
    "Hera",
    "Poseidon",
    "Demeter",
    "Athena",
    "Apollo",
    "Artemis",
    "Ares",
    "Aphrodite",
    "Hephaestus",
    "Hermes",
    "Hestia",
    "Dionysus",
    "Persephone",
    "Hades",
    "Prometheus",
    "Achilles",
    "Odysseus",
    "Heracles",
    "Perseus",
    "Theseus",
    "Orpheus",
    "Icarus",
    "Minos",
    "Medea",
    "Cassandra",
    "Electra",
    "Antigone",
    "Andromeda",
    "Atalanta",
    "Calypso",
    "Circe",
    "Daphne",
    "Echo",
    "Eurydice",
    "Galatea",
    "Hecate",
    "Iris",
    "Penelope",
    "Selene",
    "Pandora",
    "Psyche",
    "Ariadne",
    "Phaedra",
    "Niobe",
    "Io",
    "Thetis",
    "Nemesis",
    "Tyche",
    "Nike",
]

# ---------------------------------------------------------------------------
# PassMark reference data
# ---------------------------------------------------------------------------

_PASSMARK_DATA: dict[str, tuple[int, int]] | None = None  # {normalized_name: (mt, st)}
_PASSMARK_CSV = Path(__file__).parent / "data" / "passmark_cpu.csv"


def _normalize_cpu_name(name: str) -> str:
    """Normalize a CPU model string for fuzzy matching against PassMark data."""
    name = name.upper()
    # Remove trademark symbols and common noise
    for token in ("(R)", "(TM)", "CPU", "PROCESSOR", "  "):
        name = name.replace(token, " ")
    # Collapse frequency suffixes like "@ 3.00GHz" → "3.00GHZ"
    name = re.sub(r"\s*@\s*", " ", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    return name


def load_passmark_data() -> dict[str, tuple[int, int]]:
    """Load PassMark CPU scores from the bundled CSV.

    Returns a dict mapping normalized CPU name → (passmark_mt, passmark_st).
    Returns an empty dict if the CSV is missing or unreadable.
    The result is cached globally after the first call.
    """
    global _PASSMARK_DATA
    if _PASSMARK_DATA is not None:
        return _PASSMARK_DATA
    _PASSMARK_DATA = {}
    if not _PASSMARK_CSV.exists():
        return _PASSMARK_DATA
    with _PASSMARK_CSV.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(row for row in fh if not row.startswith("#"))
        for row in reader:
            raw = row.get("CPU Name", "").strip()
            if not raw:
                continue
            try:
                mt = int(row.get("Passmark (MT)", "0").replace(",", "") or 0)
                st = int(row.get("Passmark (ST)", "0").replace(",", "") or 0)
            except ValueError:
                continue
            _PASSMARK_DATA[_normalize_cpu_name(raw)] = (mt, st)
    return _PASSMARK_DATA


def lookup_passmark(cpu_model: str) -> tuple[int, int] | tuple[None, None]:
    """Return (passmark_mt, passmark_st) for a CPU model, or (None, None) if unknown.

    Matching strategy:
    1. Exact normalized match — O(1).
    2. First entry whose normalized key is a substring of the query (or vice versa),
       preferring the longest (most specific) key — O(n) over the CSV, done once.
    """
    data = load_passmark_data()
    if not data:
        return None, None
    query = _normalize_cpu_name(cpu_model)
    # Exact match (O(1))
    if query in data:
        return data[query]
    # Substring match — prefer longer keys (more specific)
    best_key: str | None = None
    best_val: tuple[int, int] | None = None
    for k, v in data.items():
        if k in query or query in k:
            if best_key is None or len(k) > len(best_key):
                best_key, best_val = k, v
    return best_val if best_val is not None else (None, None)


def anonymize_hosts(
    hosts: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Replace real hostnames with Greek mythology names.

    Returns a new dict with anonymized keys.  The ``metadata.hostname``
    field inside each host is also updated.  Build-time ``host`` fields
    are remapped as well.
    """
    mapping: dict[str, str] = {}
    for idx, hostname in enumerate(sorted(hosts.keys())):
        mapping[hostname] = _GREEK_NAMES[idx % len(_GREEK_NAMES)]

    result: dict[str, dict[str, Any]] = {}
    for real_name, anon_name in mapping.items():
        data = hosts[real_name]
        # Update metadata hostname
        if "metadata" in data and "hostname" in data["metadata"]:
            data["metadata"]["hostname"] = anon_name
        # Update build-time host references
        bt = data.get("gentoo_build_times", {})
        for pkg_info in bt.values():
            for build in pkg_info.get("builds", []):
                if build.get("host") == real_name:
                    build["host"] = anon_name
        result[anon_name] = data

    return result


def _is_higher_better(host_results: dict) -> bool:
    """Return True if this benchmark's metric is higher=better (e.g. throughput)."""
    sample = next(iter(host_results.values()), {})
    return bool(sample.get("higher_is_better", False))


def _format_throughput(mean_kb_s: float, stddev_kb_s: float = 0.0) -> str:
    """Format a KB/s throughput value with automatic unit scaling."""
    if mean_kb_s >= 1_000_000:
        return f"{mean_kb_s / 1_000_000:.2f} ± {stddev_kb_s / 1_000_000:.2f} GB/s"
    if mean_kb_s >= 1_000:
        return f"{mean_kb_s / 1_000:.1f} ± {stddev_kb_s / 1_000:.1f} MB/s"
    return f"{mean_kb_s:.0f} ± {stddev_kb_s:.0f} KB/s"


def _bench_requires_tool(bench_name: str, category: str) -> str | None:
    """Return the tool name required by a sub-benchmark, or None."""
    lower = bench_name.lower()
    for pattern, tool in _BENCH_TOOL_MAP:
        if pattern in lower:
            return tool
    if category == "ffmpeg":
        return "ffmpeg"
    if category == "imagemagick":
        return "imagemagick"
    return None


def _compute_footnotes(
    category: str,
    benchmarks: dict[str, dict[str, dict[str, float]]],
    all_hostnames: list[str],
    hosts: dict[str, dict],
) -> dict[str, list[str]]:
    """Return {hostname: [reason, ...]} for hosts with missing results in this category."""
    hosts_with_any_result: set[str] = set()
    for host_results in benchmarks.values():
        hosts_with_any_result.update(host_results.keys())

    all_bench_names = set(benchmarks.keys())
    footnotes: dict[str, list[str]] = {}

    for hostname in all_hostnames:
        meta = hosts[hostname].get("metadata", {})
        notes = hosts[hostname].get("benchmark_notes", {})
        os_family = meta.get("os_family", "")
        os_name = meta.get("os", "")
        filesystem = meta.get("filesystem", "")
        missing_opt: set[str] = set(notes.get("missing_tools", {}).get("optional", []))
        missing_req: set[str] = set(notes.get("missing_tools", {}).get("required", []))
        all_missing = missing_opt | missing_req

        reasons: list[str] = []

        if hostname not in hosts_with_any_result:
            if os_family == "Windows" and category in _WINDOWS_EXCLUDED:
                reasons.append("not available on Windows")
            elif category == "gentoo_build_times" and "gentoo" not in os_name.lower():
                reasons.append("Gentoo-only benchmark")
            elif category == "disk" and filesystem == "tmpfs":
                reasons.append("work directory is RAM-backed (tmpfs), disk I/O skipped")
            elif category in ("gimp", "inkscape", "opencv"):
                tool = category if category != "opencv" else "python3-opencv"
                reasons.append(f"{tool} not installed or not available headlessly")
            elif category == "boot_time" and os_family == "Windows":
                reasons.append("not available on Windows")
            elif any(
                cat == category for tool in all_missing for cat in _TOOL_CATEGORIES.get(tool, [])
            ):
                tools_needed = [t for t in all_missing if category in _TOOL_CATEGORIES.get(t, [])]
                reasons.append(f"required tool(s) not installed: {', '.join(sorted(tools_needed))}")
        else:
            for bench_name in all_bench_names:
                if hostname not in benchmarks.get(bench_name, {}):
                    tool = _bench_requires_tool(bench_name, category)
                    if tool and tool in all_missing:
                        reasons.append(f"{bench_name}: {tool} not installed")

        if reasons:
            footnotes[hostname] = reasons

    return footnotes


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------


def _short_version(ver_string: str) -> str:
    """Extract a compact version number from a verbose version string.

    Examples::

        "gcc (GCC) 14.2.1 20250123" -> "14.2.1"
        "Python 3.13.5"              -> "3.13.5"
        "OpenSSL 3.5.4 30 Sep 2025"  -> "3.5.4"
        "go version go1.25.7 linux/amd64" -> "1.25.7"
        "rustc 1.93.1 (01f6ddf75 2026-02-11)" -> "1.93.1"
        "clang version 21.1.8"       -> "21.1.8"
    """
    m = re.search(r"\b(\d+\.\d+(?:\.\d+)?)\b", ver_string)
    return m.group(1) if m else ver_string[:20]


def _get_category_versions(category: str, hosts_features: dict[str, dict]) -> dict[str, str]:
    """Return ``{hostname: short_version}`` for the primary tool of *category*.

    Returns an empty dict if the category has no primary tool or no version data
    is available (graceful degradation for older result sets).
    """
    tool_key: str | None = None
    for prefix, key in _CATEGORY_TOOL_VERSION.items():
        if category.startswith(prefix):
            tool_key = key
            break

    if tool_key is None:
        return {}

    result: dict[str, str] = {}
    for host, feat in hosts_features.items():
        ver_str = feat.get(f"ver_{tool_key}", "")
        if ver_str and ver_str not in ("not installed", "—", "?"):
            result[host] = _short_version(ver_str)
    return result


def _format_bench_label(command: str, category: str) -> str:
    """Format a benchmark command name into a readable label.

    For compiler categories the command name encodes flags and bench type as
    ``{cc_label}--{opt_flags}-{bench_type}`` (e.g. ``gcc-14--O3_-flto-compile``).
    Rust toolchain commands use ``{tc_label}-cargo-{mode}`` (e.g. ``stable-cargo-debug``).
    Go toolchain commands use ``{go_label}-build`` (e.g. ``go1.25-build``).
    Python commands use ``{py_version}-{bench}`` (e.g. ``py3.13-prime-sieve``).
    This function reformats those into human-readable form.  Other categories
    are returned unchanged.
    """
    if category.startswith("compiler"):
        # Pattern: cc_label--opt_flags-bench_type (e.g. gcc-14--O3_-flto-compile)
        m = re.match(r"^(\S+?)--(-\S+)-(\w+)$", command)
        if m:
            cc_label, opt_flags, bench_type = m.groups()
            opt_clean = opt_flags.replace("_", " ")
            return f"{cc_label} {opt_clean} {bench_type}"
        # Pattern without bench_type (e.g. sqlite amalgamation: gcc-14--O2)
        m2 = re.match(r"^(\S+?)--(-\S+)$", command)
        if m2:
            cc_label, opt_flags = m2.groups()
            opt_clean = opt_flags.replace("_", " ")
            return f"{cc_label} {opt_clean}"
        # Rust/Go pattern: label-bench (e.g. stable-cargo-debug, go1.25-build)
        return command.replace("-", " ")
    if category == "python":
        # Version-prefixed Python command: py3.13-prime-sieve → py3.13 prime-sieve
        m = re.match(r"^(py[\d.]+|python\d*(?:\.\d+)?)-(.+)$", command)
        if m:
            version, bench = m.groups()
            return f"{version} {bench}"
    return command


# ---------------------------------------------------------------------------
# Compiler benchmark pivot helpers
# ---------------------------------------------------------------------------

# Natural order for C compiler optimization flags.
_OPT_LEVEL_ORDER: dict[str, int] = {
    "-O0": 0,
    "-Og": 1,
    "-O1": 2,
    "-O2": 3,
    "-Os": 4,
    "-Oz": 5,
    "-O3": 6,
    "-O3 -flto": 7,
    "-O3 -floop-nest-optimize": 8,
    "-O3 -mllvm -polly": 9,
}

# Categories that use the compiler pivot layout (opt levels as columns).
_COMPILER_PIVOT_CATEGORIES: frozenset[str] = frozenset({"compiler_c_compile", "compiler_c_runtime"})


def _parse_compiler_bench(command: str) -> tuple[str, str, str] | None:
    """Parse ``{cc_label}--{opt}-{bench_type}`` → ``(cc_label, opt, bench_type)``.

    Opt flags are stored without a leading dash (e.g. ``O2``, ``O3_-flto``).
    Returns ``opt`` with underscores expanded to spaces and a ``-`` prepended
    so it matches common GCC notation (e.g. ``-O3 -flto``).
    Returns None if the command does not match the expected pattern.
    """
    m = re.match(r"^(\S+?)--(\S+?)-(\w+)$", command)
    if not m:
        return None
    cc_label, opt_raw, bench_type = m.groups()
    opt = "-" + opt_raw.replace("_", " ")
    return cc_label, opt, bench_type


def _compiler_display_version(cc_label: str, hostname: str, hosts: dict) -> str:
    """Return a short, human-readable version string for *cc_label* on *hostname*.

    Looks up ``compiler_versions.json`` data (stored in host metadata) and
    extracts the first semver token.  Falls back to *cc_label* if not found.

    Examples::

        "gcc-14 (Gentoo Hardened 14.3.1_p20260213 p5) 14.3.1 20260213"  → "gcc 14.3.1"
        "clang version 21.1.8"                                            → "clang 21.1.8"
    """
    ver_map: dict[str, str] = (
        hosts.get(hostname, {}).get("metadata", {}).get("compiler_versions", {})
    )
    full_ver = ver_map.get(cc_label, "")
    base = re.sub(r"-\d+$", "", cc_label)  # "gcc-14" → "gcc", "clang-21" → "clang"
    if full_ver:
        m = re.search(r"\b(\d+\.\d+\.\d+)\b", full_ver)
        if m:
            return f"{base} {m.group(1)}"
    return cc_label


def _sort_cc_label(cc_label: str) -> tuple[str, int]:
    """Sort key so ``gcc-14 < gcc-15 < clang-21``."""
    m = re.match(r"^([A-Za-z]+)-(\d+)$", cc_label)
    return (m.group(1), int(m.group(2))) if m else (cc_label, 0)


def _build_compiler_pivot(
    benchmarks: dict[str, dict[str, dict[str, float]]],
    hostnames: list[str],
    hosts: dict,
) -> tuple[list[str], list[tuple[str, str, str, dict[str, dict[str, float]]]]]:
    """Build the pivoted compiler benchmark structure.

    Returns:
        opt_labels: list of optimization flags sorted by ``_OPT_LEVEL_ORDER``.
        rows: list of ``(cc_label, version_display, hostname, {opt: result_dict})``,
              sorted by (compiler base name, version tuple, hostname).
    """
    entries: dict[tuple[str, str], dict[str, dict[str, float]]] = {}
    all_opts: set[str] = set()

    for bench_name, host_results in benchmarks.items():
        parsed = _parse_compiler_bench(bench_name)
        if not parsed:
            continue
        cc_label, opt, _bench_type = parsed
        all_opts.add(opt)
        for hostname, result in host_results.items():
            entries.setdefault((cc_label, hostname), {})[opt] = result

    opt_labels = sorted(all_opts, key=lambda o: (_OPT_LEVEL_ORDER.get(o, 99), o))

    def _row_sort_key(kv: tuple[tuple[str, str], Any]) -> tuple[str, tuple[int, ...], str]:
        (cc_label, hostname), _ignored = kv
        ver_display = _compiler_display_version(cc_label, hostname, hosts)
        # "gcc 14.3.1" → base="gcc", ver_tuple=(14,3,1); "clang" → ("clang", (0,))
        parts = ver_display.split(" ", 1)
        base = parts[0]
        ver_tuple: tuple[int, ...] = (
            tuple(int(x) for x in re.findall(r"\d+", parts[1]))  # type: ignore[assignment]
            if len(parts) > 1
            else (0,)
        )
        return (base, ver_tuple, hostname)

    rows = []
    for (cc_label, hostname), opt_data in sorted(entries.items(), key=_row_sort_key):
        ver_display = _compiler_display_version(cc_label, hostname, hosts)
        rows.append((cc_label, ver_display, hostname, opt_data))

    return opt_labels, rows


def _md_compiler_pivot_table(
    benchmarks: dict[str, dict[str, dict[str, float]]],
    hostnames: list[str],
    hosts: dict,
) -> str:
    """Render compiler benchmarks as a pivoted Markdown table.

    Rows = (compiler version, host); Columns = optimization levels.
    The cell showing the overall fastest time per optimization level is bolded.
    """
    opt_labels, rows = _build_compiler_pivot(benchmarks, hostnames, hosts)
    if not rows:
        return ""

    # Find fastest time per optimization level (lower is better).
    fastest_per_opt: dict[str, float] = {}
    for _cc, _ver, _host, opt_data in rows:
        for opt, result in opt_data.items():
            mn = result.get("mean", 0.0)
            if mn > 0 and (opt not in fastest_per_opt or mn < fastest_per_opt[opt]):
                fastest_per_opt[opt] = mn

    md_rows = []
    for _cc_label, ver_display, hostname, opt_data in rows:
        row = [ver_display, hostname]
        for opt in opt_labels:
            if opt in opt_data:
                r = opt_data[opt]
                cell = f"{r['mean']:.3f} ± {r['stddev']:.3f}"
                if r["mean"] > 0 and abs(r["mean"] - fastest_per_opt.get(opt, -1)) < 1e-9:
                    cell = f"**{cell}**"
            else:
                cell = "—"
            row.append(cell)
        md_rows.append(row)

    headers = ["Compiler", "Host"] + opt_labels
    return _md_table(headers, md_rows)


def _html_compiler_pivot_table(
    benchmarks: dict[str, dict[str, dict[str, float]]],
    hostnames: list[str],
    hosts: dict,
    footnotes: dict[str, list[str]] | None = None,
) -> str:
    """Render compiler benchmarks as a pivoted HTML table."""
    opt_labels, rows = _build_compiler_pivot(benchmarks, hostnames, hosts)
    if not rows:
        return ""

    fastest_per_opt: dict[str, float] = {}
    for _cc, _ver, _host, opt_data in rows:
        for opt, result in opt_data.items():
            mn = result.get("mean", 0.0)
            if mn > 0 and (opt not in fastest_per_opt or mn < fastest_per_opt[opt]):
                fastest_per_opt[opt] = mn

    header_cells = "<th>Compiler</th><th>Host</th>" + "".join(f"<th>{o}</th>" for o in opt_labels)
    html_rows = []
    for _cc_label, ver_display, hostname, opt_data in rows:
        cells = [f"<td><strong>{ver_display}</strong></td>", f"<td>{hostname}</td>"]
        for opt in opt_labels:
            if opt in opt_data:
                r = opt_data[opt]
                val = f"{r['mean']:.4f} ± {r['stddev']:.4f}"
                is_fastest = r["mean"] > 0 and abs(r["mean"] - fastest_per_opt.get(opt, -1)) < 1e-9
                cls = ' class="fastest"' if is_fastest else ""
                cells.append(f"<td{cls}>{val}</td>")
            else:
                cells.append("<td>—</td>")
        html_rows.append("        <tr>" + "".join(cells) + "</tr>")

    footnote_html = ""
    if footnotes:
        parts = [
            f"<strong>{h}</strong>: {'; '.join(footnotes[h])}" for h in hostnames if h in footnotes
        ]
        if parts:
            footnote_html = (
                f'\n    <p class="bench-footnote">Missing results — {" · ".join(parts)}</p>'
            )

    return (
        f"    <table>\n"
        f"      <thead>\n"
        f"        <tr>{header_cells}</tr>\n"
        f"      </thead>\n"
        f"      <tbody>\n"
        f"{chr(10).join(html_rows)}\n"
        f"      </tbody>\n"
        f"    </table>" + footnote_html
    )


# ---------------------------------------------------------------------------
# Python benchmark pivot helpers
# ---------------------------------------------------------------------------

# Known Python benchmark task names (used to split "{py_label}-{bench}").
_PYTHON_BENCH_NAMES: frozenset[str] = frozenset(
    {
        "prime-sieve",
        "list-comprehension",
        "dict-operations",
        "json-serde",
        "regex",
        "sha256-hash",
        "python-all",
    }
)

# Display order for Python benchmark columns.
_PYTHON_BENCH_ORDER: dict[str, int] = {
    "prime-sieve": 0,
    "list-comprehension": 1,
    "dict-operations": 2,
    "json-serde": 3,
    "regex": 4,
    "sha256-hash": 5,
    "python-all": 6,
}

# Categories rendered with the Python pivot layout.
_PYTHON_PIVOT_CATEGORIES: frozenset[str] = frozenset({"python"})

# Known Octave benchmark task names (used to split "{octave_label}-{bench}").
_OCTAVE_BENCH_NAMES: frozenset[str] = frozenset(
    {
        "matrix-multiply",
        "fft",
        "sort",
        "prime-sieve",
        "lu-decomp",
        "octave-all",
    }
)

# Display order for Octave benchmark columns.
_OCTAVE_BENCH_ORDER: dict[str, int] = {
    "matrix-multiply": 0,
    "fft": 1,
    "sort": 2,
    "prime-sieve": 3,
    "lu-decomp": 4,
    "octave-all": 5,
}

# Categories rendered with the Octave pivot layout.
_OCTAVE_PIVOT_CATEGORIES: frozenset[str] = frozenset({"octave"})


def _parse_python_bench(command: str) -> tuple[str, str] | None:
    """Parse ``{py_label}-{bench}`` → ``(py_label, bench)``.

    Identifies the bench suffix from the known set ``_PYTHON_BENCH_NAMES`` so
    that labels like ``py3.13-config`` are preserved intact.
    Returns None if no known bench suffix is found.
    """
    for bench in _PYTHON_BENCH_NAMES:
        suffix = f"-{bench}"
        if command.endswith(suffix):
            return command[: -len(suffix)], bench
    return None


def _py_label_sort_key(py_label: str) -> tuple[tuple[int, ...], bool, str]:
    """Sort key for Python labels: (version_tuple, is_config_variant, label).

    Examples::

        "py3"           → ((3,),       False, "py3")
        "py3.13"        → ((3, 13),    False, "py3.13")
        "py3.13.5"      → ((3, 13, 5), False, "py3.13.5")
        "py3.13-config" → ((3, 13),    True,  "py3.13-config")
        "py3.14"        → ((3, 14),    False, "py3.14")
    """
    is_config = py_label.endswith("-config")
    base = py_label[: -len("-config")] if is_config else py_label
    ver_tuple: tuple[int, ...] = tuple(int(x) for x in re.findall(r"\d+", base)) or (0,)
    return (ver_tuple, is_config, py_label)


def _python_display_version(py_label: str, hostname: str, hosts: dict) -> str:
    """Return a display string for *py_label* on *hostname*.

    Looks up ``python_versions.json`` data to resolve short aliases
    (e.g. ``py3.13``) to their full version (e.g. ``py3.13.5``).
    Falls back to *py_label* when no metadata is available.

    Examples::

        py_label="py3.13", version_str="Python 3.13.5"  → "py3.13.5"
        py_label="py3.14.1"                              → "py3.14.1" (already full)
    """
    ver_map: dict[str, str] = hosts.get(hostname, {}).get("metadata", {}).get("python_versions", {})
    # Labels in the JSON use the "python" prefix (e.g. "python3.13.5")
    python_label = re.sub(r"^py", "python", py_label)
    full_ver = ver_map.get(python_label, "")
    if full_ver:
        m = re.search(r"(\d+\.\d+\.\d+)", full_ver)
        if m:
            return f"py{m.group(1)}"
    return py_label


def _build_python_pivot(
    benchmarks: dict[str, dict[str, dict[str, float]]],
    hostnames: list[str],
    hosts: dict | None = None,
) -> tuple[list[str], list[tuple[str, str, dict[str, dict[str, float]]]]]:
    """Build pivoted Python benchmark data.

    Returns:
        bench_labels: benchmark names sorted by ``_PYTHON_BENCH_ORDER``.
        rows: list of ``(py_display_label, hostname, {bench: result_dict})``,
              sorted by (version tuple, is_config, hostname).
              When *hosts* is provided, *py_display_label* is resolved to the
              full patch-level version via ``python_versions.json`` metadata.
    """
    entries: dict[tuple[str, str], dict[str, dict[str, float]]] = {}
    all_benches: set[str] = set()

    for bench_name, host_results in benchmarks.items():
        parsed = _parse_python_bench(bench_name)
        if not parsed:
            continue
        py_label, bench = parsed
        all_benches.add(bench)
        for hostname, result in host_results.items():
            entries.setdefault((py_label, hostname), {})[bench] = result

    bench_labels = sorted(all_benches, key=lambda b: (_PYTHON_BENCH_ORDER.get(b, 99), b))

    rows = []
    for (py_label, hostname), bench_data in sorted(
        entries.items(), key=lambda kv: (_py_label_sort_key(kv[0][0]), kv[0][1])
    ):
        display = _python_display_version(py_label, hostname, hosts) if hosts else py_label
        rows.append((display, hostname, bench_data))

    return bench_labels, rows


def _md_python_pivot_table(
    benchmarks: dict[str, dict[str, dict[str, float]]],
    hostnames: list[str],
    hosts: dict | None = None,
) -> str:
    """Render Python benchmarks as a pivoted Markdown table.

    Rows = (Python label, host); Columns = benchmark names.
    The cell showing the overall fastest time per benchmark is bolded.
    """
    bench_labels, rows = _build_python_pivot(benchmarks, hostnames, hosts)
    if not rows:
        return ""

    fastest_per_bench: dict[str, float] = {}
    for _py_label, _host, bench_data in rows:
        for bench, result in bench_data.items():
            mn = result.get("mean", 0.0)
            if mn > 0 and (bench not in fastest_per_bench or mn < fastest_per_bench[bench]):
                fastest_per_bench[bench] = mn

    md_rows = []
    for py_label, hostname, bench_data in rows:
        row = [py_label, hostname]
        for bench in bench_labels:
            if bench in bench_data:
                r = bench_data[bench]
                cell = f"{r['mean']:.3f} ± {r['stddev']:.3f}"
                if r["mean"] > 0 and abs(r["mean"] - fastest_per_bench.get(bench, -1)) < 1e-9:
                    cell = f"**{cell}**"
            else:
                cell = "—"
            row.append(cell)
        md_rows.append(row)

    headers = ["Python", "Host"] + bench_labels
    return _md_table(headers, md_rows)


def _html_python_pivot_table(
    benchmarks: dict[str, dict[str, dict[str, float]]],
    hostnames: list[str],
    footnotes: dict[str, list[str]] | None = None,
    hosts: dict | None = None,
) -> str:
    """Render Python benchmarks as a pivoted HTML table."""
    bench_labels, rows = _build_python_pivot(benchmarks, hostnames, hosts)
    if not rows:
        return ""

    fastest_per_bench: dict[str, float] = {}
    for _py_label, _host, bench_data in rows:
        for bench, result in bench_data.items():
            mn = result.get("mean", 0.0)
            if mn > 0 and (bench not in fastest_per_bench or mn < fastest_per_bench[bench]):
                fastest_per_bench[bench] = mn

    header_cells = "<th>Python</th><th>Host</th>" + "".join(f"<th>{b}</th>" for b in bench_labels)
    html_rows = []
    for py_label, hostname, bench_data in rows:
        cells = [f"<td><strong>{py_label}</strong></td>", f"<td>{hostname}</td>"]
        for bench in bench_labels:
            if bench in bench_data:
                r = bench_data[bench]
                val = f"{r['mean']:.4f} ± {r['stddev']:.4f}"
                is_fastest = (
                    r["mean"] > 0 and abs(r["mean"] - fastest_per_bench.get(bench, -1)) < 1e-9
                )
                cls = ' class="fastest"' if is_fastest else ""
                cells.append(f"<td{cls}>{val}</td>")
            else:
                cells.append("<td>—</td>")
        html_rows.append("        <tr>" + "".join(cells) + "</tr>")

    footnote_html = ""
    if footnotes:
        parts = [
            f"<strong>{h}</strong>: {'; '.join(footnotes[h])}" for h in hostnames if h in footnotes
        ]
        if parts:
            footnote_html = (
                f'\n    <p class="bench-footnote">Missing results — {" · ".join(parts)}</p>'
            )

    return (
        f"    <table>\n"
        f"      <thead>\n"
        f"        <tr>{header_cells}</tr>\n"
        f"      </thead>\n"
        f"      <tbody>\n"
        f"{chr(10).join(html_rows)}\n"
        f"      </tbody>\n"
        f"    </table>" + footnote_html
    )


def _parse_octave_bench(command: str) -> tuple[str, str] | None:
    """Parse ``{octave_label}-{bench}`` → ``(octave_label, bench)``.

    Identifies the bench suffix from the known set ``_OCTAVE_BENCH_NAMES`` so
    that labels like ``octave-9.3`` are preserved intact.
    Returns None if no known bench suffix is found.
    """
    for bench in _OCTAVE_BENCH_NAMES:
        suffix = f"-{bench}"
        if command.endswith(suffix):
            return command[: -len(suffix)], bench
    return None


def _octave_label_sort_key(octave_label: str) -> tuple[tuple[int, ...], str]:
    """Sort key for Octave labels: (version_tuple, label).

    Examples::

        "octave-9"    → ((9,),    "octave-9")
        "octave-9.3"  → ((9, 3),  "octave-9.3")
        "octave-10.1" → ((10, 1), "octave-10.1")
    """
    ver_tuple: tuple[int, ...] = tuple(int(x) for x in re.findall(r"\d+", octave_label)) or (0,)
    return (ver_tuple, octave_label)


def _build_octave_pivot(
    benchmarks: dict[str, dict[str, dict[str, float]]],
    hostnames: list[str],
) -> tuple[list[str], list[tuple[str, str, dict[str, dict[str, float]]]]]:
    """Build pivoted Octave benchmark data.

    Returns:
        bench_labels: benchmark names sorted by ``_OCTAVE_BENCH_ORDER``.
        rows: list of ``(octave_label, hostname, {bench: result_dict})``,
              sorted by (version tuple, hostname).
    """
    entries: dict[tuple[str, str], dict[str, dict[str, float]]] = {}
    all_benches: set[str] = set()

    for bench_name, host_results in benchmarks.items():
        parsed = _parse_octave_bench(bench_name)
        if not parsed:
            continue
        octave_label, bench = parsed
        all_benches.add(bench)
        for hostname, result in host_results.items():
            entries.setdefault((octave_label, hostname), {})[bench] = result

    bench_labels = sorted(all_benches, key=lambda b: (_OCTAVE_BENCH_ORDER.get(b, 99), b))

    rows = []
    for (octave_label, hostname), bench_data in sorted(
        entries.items(), key=lambda kv: (_octave_label_sort_key(kv[0][0]), kv[0][1])
    ):
        rows.append((octave_label, hostname, bench_data))

    return bench_labels, rows


def _md_octave_pivot_table(
    benchmarks: dict[str, dict[str, dict[str, float]]],
    hostnames: list[str],
) -> str:
    """Render Octave benchmarks as a pivoted Markdown table.

    Rows = (Octave label, host); Columns = benchmark names.
    The cell showing the overall fastest time per benchmark is bolded.
    """
    bench_labels, rows = _build_octave_pivot(benchmarks, hostnames)
    if not rows:
        return ""

    fastest_per_bench: dict[str, float] = {}
    for _octave_label, _host, bench_data in rows:
        for bench, result in bench_data.items():
            mn = result.get("mean", 0.0)
            if mn > 0 and (bench not in fastest_per_bench or mn < fastest_per_bench[bench]):
                fastest_per_bench[bench] = mn

    md_rows = []
    for octave_label, hostname, bench_data in rows:
        row = [octave_label, hostname]
        for bench in bench_labels:
            if bench in bench_data:
                r = bench_data[bench]
                cell = f"{r['mean']:.3f} ± {r['stddev']:.3f}"
                if r["mean"] > 0 and abs(r["mean"] - fastest_per_bench.get(bench, -1)) < 1e-9:
                    cell = f"**{cell}**"
            else:
                cell = "—"
            row.append(cell)
        md_rows.append(row)

    headers = ["Octave", "Host"] + bench_labels
    return _md_table(headers, md_rows)


def _html_octave_pivot_table(
    benchmarks: dict[str, dict[str, dict[str, float]]],
    hostnames: list[str],
    footnotes: dict[str, list[str]] | None = None,
) -> str:
    """Render Octave benchmarks as a pivoted HTML table."""
    bench_labels, rows = _build_octave_pivot(benchmarks, hostnames)
    if not rows:
        return ""

    fastest_per_bench: dict[str, float] = {}
    for _octave_label, _host, bench_data in rows:
        for bench, result in bench_data.items():
            mn = result.get("mean", 0.0)
            if mn > 0 and (bench not in fastest_per_bench or mn < fastest_per_bench[bench]):
                fastest_per_bench[bench] = mn

    header_cells = "<th>Octave</th><th>Host</th>" + "".join(f"<th>{b}</th>" for b in bench_labels)
    html_rows = []
    for octave_label, hostname, bench_data in rows:
        cells = [f"<td><strong>{octave_label}</strong></td>", f"<td>{hostname}</td>"]
        for bench in bench_labels:
            if bench in bench_data:
                r = bench_data[bench]
                val = f"{r['mean']:.4f} ± {r['stddev']:.4f}"
                is_fastest = (
                    r["mean"] > 0 and abs(r["mean"] - fastest_per_bench.get(bench, -1)) < 1e-9
                )
                cls = ' class="fastest"' if is_fastest else ""
                cells.append(f"<td{cls}>{val}</td>")
            else:
                cells.append("<td>—</td>")
        html_rows.append("        <tr>" + "".join(cells) + "</tr>")

    footnote_html = ""
    if footnotes:
        parts = [
            f"<strong>{h}</strong>: {'; '.join(footnotes[h])}" for h in hostnames if h in footnotes
        ]
        if parts:
            footnote_html = (
                f'\n    <p class="bench-footnote">Missing results — {" · ".join(parts)}</p>'
            )

    return (
        f"    <table>\n"
        f"      <thead>\n"
        f"        <tr>{header_cells}</tr>\n"
        f"      </thead>\n"
        f"      <tbody>\n"
        f"{chr(10).join(html_rows)}\n"
        f"      </tbody>\n"
        f"    </table>" + footnote_html
    )


def load_results(base_dir: Path) -> dict[str, dict[str, Any]]:
    """Load all benchmark JSON results.

    Returns ``{hostname: {category: [results_list]}}``
    """
    results_dir = base_dir / "results"
    if not results_dir.is_dir():
        print(f"ERROR: results directory not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    hosts: dict[str, dict[str, Any]] = {}
    for host_dir in sorted(results_dir.iterdir()):
        if not host_dir.is_dir():
            continue
        hostname = host_dir.name
        hosts[hostname] = {"benchmarks": {}, "metadata": {}}

        # Load metadata
        meta_file = host_dir / "metadata.json"
        if meta_file.exists():
            with open(meta_file) as f:
                hosts[hostname]["metadata"] = json.load(f)

        # Load benchmark results
        for json_file in sorted(host_dir.glob("*.json")):
            if json_file.name == "metadata.json":
                continue
            category = json_file.stem
            try:
                with open(json_file) as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                # Try loading first valid JSON object (handles concatenated writes)
                try:
                    with open(json_file) as f:
                        raw = f.read()
                    data = json.JSONDecoder().raw_decode(raw)[0]
                    print(
                        f"  WARNING: {json_file.name} contains multiple JSON objects; using first",
                        file=sys.stderr,
                    )
                except Exception:
                    print(
                        f"  WARNING: skipping malformed JSON: {json_file}",
                        file=sys.stderr,
                    )
                    continue
            if "results" in data:
                hosts[hostname]["benchmarks"][category] = data["results"]
            elif "packages" in data:
                # Gentoo build time data
                hosts[hostname]["gentoo_build_times"] = data["packages"]
            elif "video_encoders" in data:
                # FFmpeg codec availability
                hosts[hostname]["ffmpeg_codecs"] = data
            elif json_file.name == "compiler_versions.json":
                # Merge per-binary version map into metadata for report access
                hosts[hostname].setdefault("metadata", {})["compiler_versions"] = data
            elif json_file.name == "python_versions.json":
                # Merge per-binary Python version map into metadata
                hosts[hostname].setdefault("metadata", {})["python_versions"] = data
            elif json_file.name == "boot_times.json":
                # systemd-analyze boot timing data
                hosts[hostname]["boot_times"] = data
            elif json_file.name == "benchmark_notes.json":
                hosts[hostname]["benchmark_notes"] = data

    return hosts


def build_comparison_table(
    hosts: dict[str, dict[str, Any]],
) -> dict[str, dict[str, dict[str, dict[str, float]]]]:
    """Build ``{category: {benchmark_name: {host: {mean, stddev, min, max}}}}``."""
    table: dict[str, dict[str, dict[str, dict[str, float]]]] = defaultdict(
        lambda: defaultdict(dict)
    )

    for hostname, data in hosts.items():
        for category, results in data.get("benchmarks", {}).items():
            for bench in results:
                name = bench.get("command", "unknown")
                table[category][name][hostname] = {
                    "mean": bench.get("mean", 0.0),
                    "stddev": bench.get("stddev", 0.0),
                    "min": bench.get("min", 0.0),
                    "max": bench.get("max", 0.0),
                    "median": bench.get("median", 0.0),
                    "higher_is_better": bench.get("higher_is_better", False),
                }

    return dict(table)


# ---------------------------------------------------------------------------
# Host feature summary
# ---------------------------------------------------------------------------


def extract_features(metadata: dict[str, Any]) -> dict[str, str]:
    """Extract salient features from host metadata for the summary table."""
    features: dict[str, str] = {}

    # OS information
    features["os"] = metadata.get("os", "unknown")
    os_ver = metadata.get("os_version", "")
    features["os_version"] = os_ver if os_ver else "—"
    features["os_family"] = metadata.get("os_family", "unknown")

    common_flags = metadata.get("common_flags", "") or ""
    cflags = metadata.get("cflags", "") or ""
    ldflags = metadata.get("ldflags", "") or ""

    # Optimization level
    for flag in common_flags.split():
        if flag.startswith("-O"):
            features["opt_level"] = flag
            break

    # Architecture
    for flag in common_flags.split():
        if flag.startswith("-march="):
            features["march"] = flag.split("=", 1)[1]
            break

    # LTO
    for src in (common_flags, ldflags):
        if "-flto" in src:
            if "-flto=thin" in src:
                features["lto"] = "thin"
            else:
                features["lto"] = "yes"
            break
    else:
        features["lto"] = "no"

    # Other notable flags
    notable = []
    if "-fno-semantic-interposition" in common_flags:
        notable.append("no-semantic-interposition")
    if "-pipe" in common_flags:
        notable.append("pipe")
    features["notable"] = ", ".join(notable) if notable else "—"

    # Hardening flags (from CFLAGS + LDFLAGS)
    hardening = []
    all_flags = f"{common_flags} {cflags} {ldflags}"
    if "-fstack-protector-strong" in all_flags:
        hardening.append("SSP-strong")
    elif "-fstack-protector" in all_flags:
        hardening.append("SSP")
    if "_FORTIFY_SOURCE" in all_flags:
        hardening.append("FORTIFY")
    if "-fPIE" in all_flags or "-fpie" in all_flags or "-pie" in ldflags:
        hardening.append("PIE")
    if "-fstack-clash-protection" in all_flags:
        hardening.append("stack-clash")
    if "-fcf-protection" in all_flags:
        hardening.append("CF-prot")
    if "-z,relro" in ldflags or "-z relro" in ldflags:
        if "-z,now" in ldflags or "-z now" in ldflags:
            hardening.append("full-RELRO")
        else:
            hardening.append("partial-RELRO")
    features["hardening"] = ", ".join(hardening) if hardening else "—"

    # march=native resolution
    features["march_native"] = metadata.get("march_native", "") or "—"

    # Compiler versions from metadata
    versions = metadata.get("versions", [])
    for entry in versions:
        if "=" in entry:
            key, val = entry.split("=", 1)
            features[f"ver_{key}"] = val

    features["cpu_model"] = metadata.get("cpu_model", "unknown")
    features["cpu_cores"] = str(metadata.get("cpu_cores", "?"))
    cpu_mhz = int(metadata.get("cpu_mhz", 0) or 0)
    if cpu_mhz > 0:
        features["cpu_clock"] = f"{cpu_mhz / 1000:.2f} GHz" if cpu_mhz >= 1000 else f"{cpu_mhz} MHz"
    else:
        features["cpu_clock"] = "—"

    # Kernel version (already in ver_kernel from uname -r)
    features["kernel"] = features.get("ver_kernel", "—")

    # Scheduler, filesystem, swap
    features["scheduler"] = metadata.get("scheduler", "") or "—"
    features["filesystem"] = metadata.get("filesystem", "") or "—"
    swap_val = metadata.get("swap_enabled", "")
    if isinstance(swap_val, bool):
        features["swap"] = "yes" if swap_val else "no"
    elif isinstance(swap_val, str):
        if swap_val.lower() in ("true", "yes", "enabled"):
            features["swap"] = "yes"
        elif swap_val:
            features["swap"] = "no"
        else:
            features["swap"] = "—"
    else:
        features["swap"] = "—"

    # CPU calibration (7-zip single-thread MIPS from benchmark run)
    cal_mips = int(metadata.get("calibration_mips", 0) or 0)
    features["calibration_mips"] = str(cal_mips) if cal_mips > 0 else "—"

    # PassMark reference scores (looked up from bundled CSV by CPU model)
    pm_mt, pm_st = lookup_passmark(features.get("cpu_model", ""))
    features["passmark_mt"] = str(pm_mt) if pm_mt else "—"
    features["passmark_st"] = str(pm_st) if pm_st else "—"

    # Prefer ansible_kernel over uname-based detection if available
    kver = metadata.get("kernel_version", "") or features.get("ver_kernel", "")
    features["kernel"] = kver if kver else "—"

    # Hypervisor flag — marks bare-metal hypervisor hosts in the report
    features["is_hypervisor"] = metadata.get("is_hypervisor", False)

    # Runtime / hardware environment fields
    features["cpu_governor"] = metadata.get("cpu_governor", "") or "—"
    features["cpu_cache_l3"] = metadata.get("cpu_cache_l3", "") or "—"
    features["mem_speed"] = metadata.get("mem_speed", "") or "—"
    features["io_scheduler"] = metadata.get("io_scheduler", "") or "—"
    features["mitigations"] = metadata.get("mitigations", "") or "default"
    features["preempt_model"] = metadata.get("preempt_model", "") or "—"
    features["thp"] = metadata.get("thp", "") or "—"
    features["virt_type"] = metadata.get("virt_type", "") or "—"
    features["cpu_flags_x86"] = metadata.get("cpu_flags_x86", "") or "—"
    features["gentoo_profile"] = metadata.get("gentoo_profile", "") or "—"

    numa = metadata.get("numa_nodes", "")
    features["numa_nodes"] = str(int(numa)) if str(numa).strip().isdigit() else "—"

    smt_raw = metadata.get("smt_active", "")
    if isinstance(smt_raw, bool):
        features["smt"] = "yes" if smt_raw else "no"
    elif str(smt_raw).lower() in ("true", "1", "yes"):
        features["smt"] = "yes"
    elif str(smt_raw).lower() in ("false", "0", "no"):
        features["smt"] = "no"
    else:
        features["smt"] = "—"

    # libc variant (glibc vs musl) — significant for Alpine and musl-based distros
    libc_variant = metadata.get("libc_variant", "") or ""
    libc_version = metadata.get("libc_version", "") or ""
    if libc_variant:
        features["libc"] = f"{libc_variant} {libc_version}".strip()
    else:
        features["libc"] = "—"

    # GCC configured-with: hardening and arch defaults baked into the compiler
    # gcc_config is a list like ["default-pie=yes", "default-ssp=no", "arch=x86-64"]
    gcc_config_lines = metadata.get("gcc_config", []) or []
    gcc_config: dict[str, str] = {}
    for line in gcc_config_lines:
        if "=" in str(line):
            k, v = str(line).split("=", 1)
            gcc_config[k.strip()] = v.strip()
    if gcc_config:
        pie = gcc_config.get("default-pie", "?")
        ssp = gcc_config.get("default-ssp", "?")
        arch_val = gcc_config.get("arch", gcc_config.get("with-arch", ""))
        tune_val = gcc_config.get("tune", gcc_config.get("with-tune", ""))
        parts = [f"PIE={pie}", f"SSP={ssp}"]
        if arch_val:
            parts.append(f"arch={arch_val}")
        if tune_val:
            parts.append(f"tune={tune_val}")
        if gcc_config.get("bootstrap-lto") == "yes":
            parts.append("bootstrap-lto")
        features["gcc_config"] = " ".join(parts)
    else:
        features["gcc_config"] = "—"

    # CXXFLAGS, MAKEFLAGS / parallel job count, RUSTFLAGS
    features["cxxflags"] = metadata.get("cxxflags", "") or "—"
    features["makeflags"] = metadata.get("makeflags", "") or "—"
    features["rustflags"] = metadata.get("rustflags", "") or "—"

    # Derive parallel job count from makeflags for easy display
    mf = features["makeflags"]
    m = re.search(r"-j\s*([0-9]+)", mf)
    features["parallel_jobs"] = m.group(1) if m else ("auto" if "-j" in mf else "—")

    # Per-binary compiler version map (populated from compiler_versions.json)
    features["compiler_versions"] = metadata.get("compiler_versions", {})  # type: ignore[assignment]

    return features


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

#: Default category weights used when no weights file is found.
_DEFAULT_WEIGHTS: dict[str, float] = {
    "compiler": 3.0,
    "linker": 2.0,
    "compression": 2.0,
    "crypto": 2.0,
    "memory": 2.0,
    "disk": 2.0,
    "ffmpeg": 1.0,
    "ffmpeg_video_encode": 1.0,
    "ffmpeg_video_decode": 1.0,
    "ffmpeg_audio_encode": 1.0,
    "ffmpeg_audio_decode": 1.0,
    "imagemagick": 1.0,
    "opencv": 1.0,
    "python": 1.0,
    "numeric": 1.0,
    "sqlite": 1.0,
    "coreutils": 1.0,
    "git": 1.0,
    "startup": 1.0,
    "process": 1.0,
    "gentoo_build_times": 0.0,  # excluded — not hyperfine data
}


def load_scoring_weights(weights_path: Path | None) -> dict[str, float]:
    """Load category weights from a YAML file.

    Falls back to :data:`_DEFAULT_WEIGHTS` if the file is absent or cannot
    be parsed (requires PyYAML; silently falls back if not installed).
    """
    if weights_path is None or not weights_path.exists():
        return dict(_DEFAULT_WEIGHTS)
    try:
        import yaml  # type: ignore[import-untyped]

        with open(weights_path) as f:
            data = yaml.safe_load(f)
        weights = data.get("weights", {})
        return {str(k): float(v) for k, v in weights.items()}
    except Exception as exc:
        print(f"WARNING: could not load weights file {weights_path}: {exc}", file=sys.stderr)
        return dict(_DEFAULT_WEIGHTS)


def compute_scores(
    table: dict[str, dict[str, dict[str, dict[str, float]]]],
    weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """Compute a weighted performance score for each host.

    For every benchmark the host participated in::

        bench_score = min_time_across_all_hosts / host_time * 100

    The fastest host scores 100; a host twice as slow scores 50.

    Scores are averaged per category, then a weighted average is taken across
    all categories using *weights* (defaults to :data:`_DEFAULT_WEIGHTS`).

    Returns ``{hostname: score}`` where scores are in the range (0, 100].
    A host that only participated in a subset of benchmarks is scored only on
    those it ran; missing benchmarks are not penalised.
    """
    if weights is None:
        weights = _DEFAULT_WEIGHTS

    # category → hostname → list[bench_score]
    cat_scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for category, benchmarks in table.items():
        for _bench_name, host_results in benchmarks.items():
            valid = {h: r["mean"] for h, r in host_results.items() if r.get("mean", 0) > 0}
            if not valid:
                continue
            higher = _is_higher_better(host_results)
            if higher:
                best = max(valid.values())
                for hostname, t in valid.items():
                    cat_scores[category][hostname].append(t / best * 100)
            else:
                min_time = min(valid.values())
                for hostname, t in valid.items():
                    cat_scores[category][hostname].append(min_time / t * 100)

    # Collect all hostnames seen
    all_hosts: set[str] = set()
    for hmap in cat_scores.values():
        all_hosts.update(hmap)

    scores: dict[str, float] = {}
    for hostname in all_hosts:
        weighted_sum = 0.0
        weight_total = 0.0
        for category, hmap in cat_scores.items():
            w = weights.get(category, 1.0)
            if w <= 0:
                continue
            if hostname not in hmap:
                continue
            cat_avg = sum(hmap[hostname]) / len(hmap[hostname])
            weighted_sum += cat_avg * w
            weight_total += w
        scores[hostname] = weighted_sum / weight_total if weight_total > 0 else 0.0

    return scores


def _score_badge_html(score: float, rank: int) -> str:
    """Return an HTML cell value for a score with rank medal and colour."""
    medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "")
    # Gradient: 100 → green (#00e676), 50 → amber (#ffa726), 0 → red (#ef5350)
    if score >= 75:
        r, g, b = 0, 230, 118  # green
    elif score >= 50:
        t = (score - 50) / 25
        r = int(255 * (1 - t))
        g = int(167 + 63 * t)
        b = int(38 * (1 - t))
    else:
        t = score / 50
        r = 239
        g = int(83 * t)
        b = int(32 * t + 53 * (1 - t))
    color = f"rgb({r},{g},{b})"
    return f'<strong style="color:{color}">{medal} {score:.1f}</strong>'


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a Markdown table with alignment."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))

    sep = "| " + " | ".join("-" * w for w in widths) + " |"
    hdr = "| " + " | ".join(h.ljust(w) for h, w in zip(headers, widths, strict=False)) + " |"
    lines = [hdr, sep]
    for row in rows:
        padded = [cell.ljust(widths[i]) if i < len(widths) else cell for i, cell in enumerate(row)]
        lines.append("| " + " | ".join(padded) + " |")
    return "\n".join(lines)


def _collect_build_times(
    hosts: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Aggregate Gentoo build time data across all hosts.

    Returns ``{package_name: [entries]}`` where each entry has
    host, version, duration_secs, kernel, compiler, timestamp.
    """
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for hostname, host_data in hosts.items():
        bt = host_data.get("gentoo_build_times", {})
        for pkg_name, pkg_info in bt.items():
            for build in pkg_info.get("builds", []):
                result[pkg_name].append(
                    {
                        "host": hostname,
                        "version": build.get("version", "?"),
                        "duration_secs": build.get("duration_secs", 0),
                        "kernel": build.get("kernel", "unknown"),
                        "compiler": build.get("compiler", "unknown"),
                        "timestamp": build.get("timestamp", 0),
                    }
                )
    return dict(result)


def _collect_codec_availability(
    hosts: dict[str, dict[str, Any]],
) -> dict[str, dict[str, list[str]]]:
    """Aggregate FFmpeg codec availability across hosts.

    Returns ``{hostname: {category: [codec_names]}}`` for hosts that have
    ``ffmpeg_codecs`` data.
    """
    result: dict[str, dict[str, list[str]]] = {}
    for hostname, host_data in hosts.items():
        codecs = host_data.get("ffmpeg_codecs")
        if codecs:
            result[hostname] = codecs
    return result


# ---------------------------------------------------------------------------
# Compiler optimization analysis
# ---------------------------------------------------------------------------

_RUNTIME_ANALYSIS_FLAGS = ["-O3", "-O3 -flto", "-O3 -floop-nest-optimize", "-O3 -mllvm -polly"]
_COMPILE_ANALYSIS_FLAGS = ["-O3", "-O3 -flto", "-O3 -floop-nest-optimize", "-O3 -mllvm -polly"]
_O2_BASELINE = "-O2"


def _md_compiler_analysis(
    table: dict[str, dict[str, dict[str, dict[str, float]]]],
    hostnames: list[str],
    hosts: dict,
) -> str:
    """Generate a Markdown section with compiler optimization analysis.

    Produces a delta table (% change vs -O2 baseline) for both runtime and
    compile-time, followed by prose commentary and a "best option per host"
    summary.
    """
    compile_benchmarks = table.get("compiler_c_compile", {})
    runtime_benchmarks = table.get("compiler_c_runtime", {})
    if not runtime_benchmarks:
        return ""

    _unused_opt_labels_rt, runtime_rows = _build_compiler_pivot(
        runtime_benchmarks, hostnames, hosts
    )
    _unused_opt_labels_ct, compile_rows = _build_compiler_pivot(
        compile_benchmarks, hostnames, hosts
    )

    # Index data by (cc_label, hostname)
    runtime_data: dict[tuple[str, str], dict[str, float]] = {}
    ver_display: dict[tuple[str, str], str] = {}
    for cc_label, ver, hostname, opt_data in runtime_rows:
        key = (cc_label, hostname)
        runtime_data[key] = {opt: res["mean"] for opt, res in opt_data.items() if res.get("mean")}
        ver_display[key] = ver

    compile_data: dict[tuple[str, str], dict[str, float]] = {}
    for cc_label, _ver, hostname, opt_data in compile_rows:
        key = (cc_label, hostname)
        compile_data[key] = {opt: res["mean"] for opt, res in opt_data.items() if res.get("mean")}

    # Determine which analysis flags actually have data
    all_keys = sorted(runtime_data.keys(), key=lambda k: (_sort_cc_label(k[0]), k[1]))
    active_rt_flags = [
        f
        for f in _RUNTIME_ANALYSIS_FLAGS
        if any(
            f in runtime_data.get(k, {}) and _O2_BASELINE in runtime_data.get(k, {})
            for k in all_keys
        )
    ]
    active_ct_flags = [
        f
        for f in _COMPILE_ANALYSIS_FLAGS
        if any(
            f in compile_data.get(k, {}) and _O2_BASELINE in compile_data.get(k, {})
            for k in all_keys
        )
    ]

    if not active_rt_flags:
        return ""

    def _pct_delta(new_val: float, baseline: float) -> str | None:
        """Return formatted % delta string, or None if inputs are invalid."""
        if not baseline or not new_val:
            return None
        return f"{(new_val - baseline) / baseline * 100:+.1f}%"

    # Build delta table
    rt_headers = [f"RT {f} vs -O2" for f in active_rt_flags]
    ct_headers = [f"CT {f} vs -O2" for f in active_ct_flags]
    headers = ["Compiler", "Host"] + rt_headers + ct_headers

    table_rows: list[list[str]] = []
    for key in all_keys:
        cc_label, hostname = key
        rt = runtime_data.get(key, {})
        ct = compile_data.get(key, {})
        rt_baseline = rt.get(_O2_BASELINE)
        ct_baseline = ct.get(_O2_BASELINE)

        row: list[str] = [ver_display.get(key, cc_label), hostname]

        for flag in active_rt_flags:
            val = rt.get(flag)
            delta_str = _pct_delta(val, rt_baseline) if rt_baseline and val else None
            if delta_str is None:
                row.append("—")
            else:
                # Negative % = faster = improvement; bold if > 2% improvement
                pct = (val - rt_baseline) / rt_baseline * 100  # type: ignore[operator]
                if pct < -2.0:
                    row.append(f"**{delta_str}**")
                else:
                    row.append(delta_str)

        for flag in active_ct_flags:
            val = ct.get(flag)
            delta_str = _pct_delta(val, ct_baseline) if ct_baseline and val else None
            row.append(delta_str if delta_str is not None else "—")

        table_rows.append(row)

    lines: list[str] = []
    lines.append("## Compiler Optimization Analysis")
    lines.append("")
    lines.append(
        "Delta vs -O2 baseline. "
        "RT = runtime, CT = compile time. "
        "Negative runtime % = faster. "
        "**Bold** = >2% runtime improvement."
    )
    lines.append("")
    lines.append(_md_table(headers, table_rows))
    lines.append("")

    # --- Prose commentary ---
    # Collect per-(key, flag) deltas for median computation
    def _collect_deltas(
        data: dict[tuple[str, str], dict[str, float]],
        flags: list[str],
    ) -> dict[str, list[float]]:
        """Return {flag: [pct_delta, ...]} across all (cc_label, hostname) pairs."""
        result: dict[str, list[float]] = {f: [] for f in flags}
        for key in all_keys:
            d = data.get(key, {})
            baseline = d.get(_O2_BASELINE)
            if not baseline:
                continue
            for flag in flags:
                val = d.get(flag)
                if val:
                    result[flag].append((val - baseline) / baseline * 100)
        return result

    rt_deltas = _collect_deltas(runtime_data, active_rt_flags)
    ct_deltas = _collect_deltas(compile_data, active_ct_flags)

    def _median(values: list[float]) -> float | None:
        if not values:
            return None
        s = sorted(values)
        mid = len(s) // 2
        return (s[mid - 1] + s[mid]) / 2.0 if len(s) % 2 == 0 else s[mid]

    lines.append("### Commentary")
    lines.append("")

    # -O3 vs -O2
    rt_o3 = _median(rt_deltas.get("-O3", []))
    ct_o3 = _median(ct_deltas.get("-O3", []))
    if rt_o3 is not None:
        rt_str = f"{rt_o3:+.1f}%"
        ct_str = f"{ct_o3:+.1f}%" if ct_o3 is not None else "unknown"
        lines.append(
            f"- **-O3 vs -O2**: Median {rt_str} runtime change; compile time {ct_str}. "
            "Recommended as the default for optimised builds."
        )

    # -O3 -flto vs -O2
    rt_flto = _median(rt_deltas.get("-O3 -flto", []))
    ct_flto = _median(ct_deltas.get("-O3 -flto", []))
    if rt_flto is not None:
        rt_str = f"{rt_flto:+.1f}%"
        ct_str = f"{ct_flto:+.1f}%" if ct_flto is not None else "unknown"
        if rt_flto < -2.0:
            lines.append(
                f"- **-O3 -flto vs -O3**: LTO adds a median {rt_str} runtime improvement "
                f"at the cost of {ct_str} longer compile. "
                "Worthwhile for long-running processes."
            )
        else:
            lines.append(
                f"- **-O3 -flto vs -O3**: LTO shows minimal benefit on this workload "
                f"(median {rt_str}). "
                f"The compile overhead ({ct_str}) is likely not justified unless "
                "link-time inlining is expected to help."
            )

    # GCC Graphite
    rt_graphite = _median(rt_deltas.get("-O3 -floop-nest-optimize", []))
    ct_graphite = _median(ct_deltas.get("-O3 -floop-nest-optimize", []))
    if rt_graphite is not None:
        rt_str = f"{rt_graphite:+.1f}%"
        magnitude = abs(rt_graphite)
        if magnitude > 5.0:
            effect = "a substantial effect"
        elif magnitude > 2.0:
            effect = "a moderate effect"
        else:
            effect = "minimal effect"
        ct_str = f"{ct_graphite:+.1f}%" if ct_graphite is not None else "unknown"
        lines.append(
            f"- **-O3 -floop-nest-optimize (GCC Graphite)**: "
            f"Polyhedral loop optimizer shows a median {rt_str} runtime change "
            f"({effect}; compile overhead {ct_str}). "
            "Best suited for loop-heavy numeric workloads."
        )

    # Clang Polly
    rt_polly = _median(rt_deltas.get("-O3 -mllvm -polly", []))
    ct_polly = _median(ct_deltas.get("-O3 -mllvm -polly", []))
    if rt_polly is not None:
        rt_str = f"{rt_polly:+.1f}%"
        magnitude = abs(rt_polly)
        if magnitude > 5.0:
            effect = "a substantial effect"
        elif magnitude > 2.0:
            effect = "a moderate effect"
        else:
            effect = "minimal effect"
        ct_str = f"{ct_polly:+.1f}%" if ct_polly is not None else "unknown"
        lines.append(
            f"- **-O3 -mllvm -polly (Clang Polly)**: "
            f"Polyhedral loop optimizer shows a median {rt_str} runtime change "
            f"({effect}; compile overhead {ct_str}). "
            "Best suited for loop-heavy numeric workloads."
        )

    lines.append("")

    # --- Best option per host ---
    candidate_flags = [_O2_BASELINE] + active_rt_flags
    best_rows: list[list[str]] = []
    for hostname in hostnames:
        best_mean: float | None = None
        best_cc = "—"
        best_flag = "—"
        best_delta_str = "—"

        for key in all_keys:
            cc_label, khost = key
            if khost != hostname:
                continue
            rt = runtime_data.get(key, {})
            o2_mean = rt.get(_O2_BASELINE)
            for flag in candidate_flags:
                val = rt.get(flag)
                if val is not None and (best_mean is None or val < best_mean):
                    best_mean = val
                    best_cc = ver_display.get(key, cc_label)
                    best_flag = flag
                    if o2_mean and flag != _O2_BASELINE:
                        best_delta_str = f"{(val - o2_mean) / o2_mean * 100:+.1f}%"
                    else:
                        best_delta_str = "baseline"

        best_rows.append([hostname, best_cc, best_flag, best_delta_str])

    if best_rows:
        lines.append("### Best Option Per Host")
        lines.append("")
        lines.append(_md_table(["Host", "Best Compiler", "Best Flag", "Runtime vs -O2"], best_rows))
        lines.append("")

    return "\n".join(lines)


def generate_markdown(
    hosts: dict[str, dict[str, Any]],
    table: dict[str, dict[str, dict[str, dict[str, float]]]],
    scores: dict[str, float] | None = None,
) -> str:
    """Generate the full Markdown report."""
    lines: list[str] = []
    timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")

    # Sort hosts by score descending (unscored hosts sort last)
    if scores:
        hostnames = sorted(hosts.keys(), key=lambda h: scores.get(h, -1), reverse=True)
    else:
        hostnames = sorted(hosts.keys())

    lines.append("# Gentoo VM Benchmark Report")
    lines.append("")
    lines.append(f"*Generated: {timestamp}*")
    lines.append("")

    # --- Host summary table ---
    lines.append("## Host Configuration Summary")
    lines.append("")

    summary_headers = [
        "Rank",
        "Host",
        "Score",
        "OS",
        "Kernel",
        "CPU",
        "Clock",
        "Cores",
        "Opt",
        "March",
        "March (native)",
        "LTO",
        "Hardening",
        "Scheduler",
        "Filesystem",
        "Swap",
        "7z MIPS",
        "PassMark (ST)",
        "PassMark (MT)",
        "GCC",
        "Clang",
    ]
    summary_rows: list[list[str]] = []
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    for rank, hostname in enumerate(hostnames, 1):
        meta = hosts[hostname].get("metadata", {})
        feat = extract_features(meta)
        os_label = feat.get("os", "?")
        if feat.get("os_version", "—") != "—":
            os_label += " " + feat["os_version"]
        hv_prefix = "[HV] " if feat.get("is_hypervisor") else ""
        score_str = f"{scores[hostname]:.1f}" if scores and hostname in scores else "—"
        rank_str = medals.get(rank, str(rank)) if scores else "—"
        summary_rows.append(
            [
                rank_str,
                hv_prefix + hostname,
                score_str,
                os_label,
                feat.get("kernel", "—"),
                feat.get("cpu_model", "?")[:40],
                feat.get("cpu_clock", "—"),
                feat.get("cpu_cores", "?"),
                feat.get("opt_level", "—"),
                feat.get("march", "—"),
                feat.get("march_native", "—"),
                feat.get("lto", "—"),
                feat.get("hardening", "—"),
                feat.get("scheduler", "—"),
                feat.get("filesystem", "—"),
                feat.get("swap", "—"),
                feat.get("calibration_mips", "—"),
                feat.get("passmark_st", "—"),
                feat.get("passmark_mt", "—"),
                feat.get("ver_gcc", "?")[:20],
                feat.get("ver_clang", "?")[:20],
            ]
        )
    lines.append(_md_table(summary_headers, summary_rows))
    lines.append("")

    # --- Runtime environment table ---
    lines.append("## Host Runtime Environment")
    lines.append("")
    env_headers = [
        "Host",
        "Virt",
        "Governor",
        "SMT",
        "THP",
        "Mitigations",
        "Preempt",
        "I/O Sched",
        "NUMA",
        "Mem Speed",
        "L3 Cache",
        "CPU_FLAGS_X86",
    ]
    env_rows: list[list[str]] = []
    for hostname in hostnames:
        meta = hosts[hostname].get("metadata", {})
        feat = extract_features(meta)
        hv_prefix = "[HV] " if feat.get("is_hypervisor") else ""
        env_rows.append(
            [
                hv_prefix + hostname,
                feat.get("virt_type", "—"),
                feat.get("cpu_governor", "—"),
                feat.get("smt", "—"),
                feat.get("thp", "—"),
                feat.get("mitigations", "default"),
                feat.get("preempt_model", "—"),
                feat.get("io_scheduler", "—"),
                feat.get("numa_nodes", "—"),
                feat.get("mem_speed", "—"),
                feat.get("cpu_cache_l3", "—"),
                feat.get("cpu_flags_x86", "—")[:50],
            ]
        )
    lines.append(_md_table(env_headers, env_rows))
    lines.append("")

    # --- FFmpeg codec availability ---
    codec_avail = _collect_codec_availability(hosts)
    if codec_avail:
        lines.append("## FFmpeg Codec Availability")
        lines.append("")
        avail_hosts = sorted(codec_avail.keys())
        for group_key, group_title in [
            ("video_encoders", "Video Encoders"),
            ("video_decoders", "Video Decoders"),
            ("audio_encoders", "Audio Encoders"),
            ("audio_decoders", "Audio Decoders"),
        ]:
            all_codecs: set[str] = set()
            for hdata in codec_avail.values():
                all_codecs.update(hdata.get(group_key, []))
            if not all_codecs:
                continue
            lines.append(f"### {group_title}")
            lines.append("")
            ca_headers = ["Codec"] + avail_hosts
            ca_rows: list[list[str]] = []
            for codec in sorted(all_codecs):
                row = [codec]
                for h in avail_hosts:
                    row.append("✓" if codec in codec_avail[h].get(group_key, []) else "—")
                ca_rows.append(row)
            lines.append(_md_table(ca_headers, ca_rows))
            lines.append("")

    # --- Per-category benchmark tables ---
    # Pre-compute host features once for version row annotation
    all_host_features_md = {h: extract_features(hosts[h].get("metadata", {})) for h in hostnames}

    for category in sorted(table.keys()):
        title = CATEGORY_TITLES.get(category, category.replace("_", " ").title())
        benchmarks = table[category]
        lines.append(f"## {title}")
        lines.append("")

        # Compiler categories use a pivoted layout: rows=(compiler, host), cols=opt levels.
        if category in _COMPILER_PIVOT_CATEGORIES:
            lines.append(
                "Times in seconds (mean ± stddev). **Lowest** per optimization level is bold."
            )
            lines.append("")
            lines.append(_md_compiler_pivot_table(benchmarks, hostnames, hosts))
            footnotes = _compute_footnotes(category, benchmarks, hostnames, hosts)
            if footnotes:
                lines.append("")
                fn_parts = [
                    f"**{h}**: {'; '.join(footnotes[h])}" for h in hostnames if h in footnotes
                ]
                if fn_parts:
                    lines.append(f"*Missing results — {' · '.join(fn_parts)}*")
            lines.append("")
            continue

        if category in _PYTHON_PIVOT_CATEGORIES:
            lines.append("Times in seconds (mean ± stddev). **Lowest** per benchmark is bold.")
            lines.append("")
            lines.append(_md_python_pivot_table(benchmarks, hostnames, hosts))
            footnotes = _compute_footnotes(category, benchmarks, hostnames, hosts)
            if footnotes:
                lines.append("")
                fn_parts = [
                    f"**{h}**: {'; '.join(footnotes[h])}" for h in hostnames if h in footnotes
                ]
                if fn_parts:
                    lines.append(f"*Missing results — {' · '.join(fn_parts)}*")
            lines.append("")
            continue

        if category in _OCTAVE_PIVOT_CATEGORIES:
            lines.append("Times in seconds (mean ± stddev). **Lowest** per benchmark is bold.")
            lines.append("")
            lines.append(_md_octave_pivot_table(benchmarks, hostnames))
            footnotes = _compute_footnotes(category, benchmarks, hostnames, hosts)
            if footnotes:
                lines.append("")
                fn_parts = [
                    f"**{h}**: {'; '.join(footnotes[h])}" for h in hostnames if h in footnotes
                ]
                if fn_parts:
                    lines.append(f"*Missing results — {' · '.join(fn_parts)}*")
            lines.append("")
            continue

        # Detect whether this category uses throughput metrics
        sample_bench = next(iter(benchmarks.values()), {})
        higher = _is_higher_better(sample_bench)

        if higher:
            lines.append("Throughput in KB/s (mean ± stddev). **Highest** is bold.")
        else:
            lines.append("Times in seconds (mean ± stddev). **Lowest** is bold.")
        lines.append("")

        headers = ["Benchmark"] + hostnames
        rows: list[list[str]] = []

        # Optional version row at top of table
        cat_versions = _get_category_versions(category, all_host_features_md)
        if cat_versions:
            ver_row = ["**Tool version**"]
            for hostname in hostnames:
                ver_row.append(cat_versions.get(hostname, "—"))
            rows.append(ver_row)

        for bench_name in sorted(benchmarks.keys()):
            host_results = benchmarks[bench_name]
            row = [_format_bench_label(bench_name, category)]

            # Find the best host for this benchmark
            means = {h: r["mean"] for h, r in host_results.items() if r["mean"] > 0}
            best = (max if higher else min)(means, key=means.get) if means else None

            for hostname in hostnames:
                if hostname in host_results:
                    r = host_results[hostname]
                    if higher:
                        cell = _format_throughput(r["mean"], r["stddev"])
                    else:
                        cell = f"{r['mean']:.3f} ± {r['stddev']:.3f}"
                    if hostname == best:
                        cell = f"**{cell}**"
                else:
                    cell = "—"
                row.append(cell)

            rows.append(row)

        lines.append(_md_table(headers, rows))

        # Footnotes for missing results
        footnotes = _compute_footnotes(category, benchmarks, hostnames, hosts)
        if footnotes:
            lines.append("")
            fn_parts = []
            for hostname in hostnames:
                if hostname in footnotes:
                    fn_parts.append(f"**{hostname}**: {'; '.join(footnotes[hostname])}")
            if fn_parts:
                lines.append(f"*Missing results — {' · '.join(fn_parts)}*")
        lines.append("")

    # --- Gentoo build time analysis ---
    build_time_data = _collect_build_times(hosts)
    if build_time_data:
        lines.append("## Gentoo Package Build Times")
        lines.append("")
        lines.append(
            "Packages with longest build time > 5 minutes. "
            "Last 3 builds shown with kernel and compiler at build time."
        )
        lines.append("")

        for pkg_name in sorted(build_time_data.keys()):
            pkg_info = build_time_data[pkg_name]
            lines.append(f"### {pkg_name}")
            lines.append("")
            bt_headers = ["Host", "Version", "Date", "Duration", "Kernel", "Compiler"]
            bt_rows: list[list[str]] = []
            for entry in sorted(pkg_info, key=lambda e: (e["host"], e["timestamp"])):
                dur = entry["duration_secs"]
                dur_str = f"{dur // 60}m {dur % 60:02d}s"
                ts = entry.get("timestamp", 0)
                date_str = (
                    datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d") if ts > 0 else "—"
                )
                bt_rows.append(
                    [
                        entry["host"],
                        entry["version"],
                        date_str,
                        dur_str,
                        entry["kernel"],
                        entry["compiler"],
                    ]
                )
            lines.append(_md_table(bt_headers, bt_rows))
            lines.append("")

    # --- Compiler optimization analysis ---
    compiler_analysis = _md_compiler_analysis(table, hostnames, hosts)
    if compiler_analysis:
        lines.append(compiler_analysis)

    # --- System boot times ---
    boot_data = {h: hosts[h]["boot_times"] for h in hostnames if hosts[h].get("boot_times")}
    if boot_data:
        lines.append("## System Boot Times")
        lines.append("")
        lines.append(
            "Measured at benchmark time. "
            "Times in seconds. **Lowest total** is bold. "
            "`systemd-analyze` gives a full phase breakdown; "
            "`dmesg` provides kernel and early-userspace phases only "
            "(firmware/loader/graphical unavailable, service blame not available)."
        )
        lines.append("")
        bth_headers = [
            "Host",
            "Method",
            "Firmware",
            "Loader",
            "Kernel",
            "Userspace",
            "Graphical",
            "Total",
        ]
        bth_rows: list[list[str]] = []
        boot_totals = {
            h: d["total_sec"]
            for h, d in boot_data.items()
            if d.get("available") and d.get("total_sec") is not None
        }
        fastest_boot = min(boot_totals, key=boot_totals.__getitem__) if boot_totals else None

        def _fmt_bt(v: float | None) -> str:
            return f"{v:.3f}" if v is not None else "—"

        for hostname in hostnames:
            d = boot_data.get(hostname)
            if not d or not d.get("available"):
                bth_rows.append([hostname, "—", "—", "—", "—", "—", "—", "—"])
                continue
            total_str = _fmt_bt(d.get("total_sec"))
            if hostname == fastest_boot:
                total_str = f"**{total_str}**"
            bth_rows.append(
                [
                    hostname,
                    d.get("method", "—"),
                    _fmt_bt(d.get("firmware_sec")),
                    _fmt_bt(d.get("loader_sec")),
                    _fmt_bt(d.get("kernel_sec")),
                    _fmt_bt(d.get("userspace_sec")),
                    _fmt_bt(d.get("graphical_sec")),
                    total_str,
                ]
            )
        lines.append(_md_table(bth_headers, bth_rows))
        lines.append("")

        any_services = any(d.get("top_services") for d in boot_data.values() if d)
        if any_services:
            lines.append("### Slowest Services at Boot")
            lines.append("")
            for hostname in hostnames:
                d = boot_data.get(hostname)
                services = (d.get("top_services") or []) if d else []
                if not services:
                    continue
                lines.append(f"**{hostname}**")
                lines.append("")
                svc_rows = [[s["name"], f"{s['time_sec']:.3f}"] for s in services[:10]]
                lines.append(_md_table(["Service", "Time (s)"], svc_rows))
                lines.append("")

    return "\n".join(lines)


# HTML report
# ---------------------------------------------------------------------------


def _color_for(idx: int) -> str:
    return CHART_COLORS[idx % len(CHART_COLORS)]


# Badge injected next to hypervisor hostnames in HTML tables
_HV_BADGE = (
    ' <span style="background:#5c4200;color:#ffd600;font-size:0.75em;'
    'padding:1px 5px;border-radius:3px;vertical-align:middle">HV</span>'
)


def generate_html(
    hosts: dict[str, dict[str, Any]],
    table: dict[str, dict[str, dict[str, dict[str, float]]]],
    scores: dict[str, float] | None = None,
) -> str:
    """Generate an interactive HTML report with Chart.js."""
    # Sort hosts by score descending (unscored hosts sort last)
    if scores:
        hostnames = sorted(hosts.keys(), key=lambda h: scores.get(h, -1), reverse=True)
    else:
        hostnames = sorted(hosts.keys())
    timestamp = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M UTC")

    # Pre-build Chart.js datasets per category
    chart_blocks: list[str] = []
    chart_id = 0

    html_sections: list[str] = []

    # Build embedded JS data structures for interactive filtering
    host_meta_for_js: dict[str, dict] = {}
    for hostname in hostnames:
        meta = hosts[hostname].get("metadata", {})
        host_meta_for_js[hostname] = {
            "os_family": meta.get("os_family", "Unknown"),
            "os": meta.get("os", "Unknown"),
        }

    bench_data_for_js: dict[str, dict] = {}
    for _cat, _benchmarks in table.items():
        bench_data_for_js[_cat] = {}
        for _bench, _host_results in _benchmarks.items():
            bench_data_for_js[_cat][_bench] = {
                h: {
                    "mean": round(r["mean"], 6),
                    "stddev": round(r["stddev"], 6),
                    "higher_is_better": r.get("higher_is_better", False),
                }
                for h, r in _host_results.items()
            }

    # --- Host summary ---
    summary_html = _html_host_summary(hosts, hostnames, scores)

    # Pre-compute host features once for version row annotation across all categories
    all_host_features_html = {h: extract_features(hosts[h].get("metadata", {})) for h in hostnames}

    # --- Per-category sections ---
    for category in sorted(table.keys()):
        title = CATEGORY_TITLES.get(category, category.replace("_", " ").title())
        benchmarks = table[category]
        bench_names = sorted(benchmarks.keys())
        chart_id += 1
        canvas_id = f"chart_{chart_id}"

        # ---------------------------------------------------------------
        # Compiler categories use a pivoted layout: rows=(compiler, host),
        # columns=optimization levels. Rewrite datasets accordingly.
        # ---------------------------------------------------------------
        if category in _COMPILER_PIVOT_CATEGORIES:
            opt_labels, pivot_rows = _build_compiler_pivot(benchmarks, hostnames, hosts)
            labels_json = json.dumps(opt_labels)
            datasets_pivot: list[dict[str, Any]] = []
            for pidx, (_cc_label, ver_display, hostname, opt_data) in enumerate(pivot_rows):
                data_points_p: list[float | None] = []
                error_bars_p: list[float | None] = []
                for opt in opt_labels:
                    if opt in opt_data:
                        data_points_p.append(round(opt_data[opt]["mean"], 4))
                        error_bars_p.append(round(opt_data[opt]["stddev"], 4))
                    else:
                        data_points_p.append(None)
                        error_bars_p.append(None)
                # Vary colour by index; add hostname suffix when multiple hosts.
                datasets_pivot.append(
                    {
                        "label": f"{ver_display} ({hostname})",
                        "data": data_points_p,
                        "backgroundColor": _color_for(pidx) + "cc",
                        "borderColor": _color_for(pidx),
                        "borderWidth": 1,
                    }
                )
            datasets_json = json.dumps(datasets_pivot, indent=2)

            footnotes = _compute_footnotes(category, benchmarks, hostnames, hosts)
            table_html = _html_compiler_pivot_table(benchmarks, hostnames, hosts, footnotes)
            section = f"""
    <section id="cat-{category}">
      <h2>{title}</h2>
      <div class="chart-container">
        <canvas id="{canvas_id}"></canvas>
      </div>
      {table_html}
    </section>"""
            html_sections.append(section)

            chart_blocks.append(f"""
    CHARTS['{canvas_id}'] = new Chart(document.getElementById('{canvas_id}'), {{
      type: 'bar',
      data: {{
        labels: {labels_json},
        datasets: {datasets_json}
      }},
      options: {{
        responsive: true,
        plugins: {{
          legend: {{ display: true }},
          title: {{ display: true, text: '{title} (seconds, lower is better)' }}
        }},
        scales: {{
          y: {{ title: {{ display: true, text: 'Time (seconds)' }} }}
        }}
      }}
    }});""")
            continue

        # Python category uses a pivoted layout: rows=(py_label, host),
        # columns=benchmark names.
        if category in _PYTHON_PIVOT_CATEGORIES:
            bench_labels, py_pivot_rows = _build_python_pivot(benchmarks, hostnames, hosts)
            labels_json = json.dumps(bench_labels)
            py_datasets: list[dict[str, Any]] = []
            for pidx, (py_label, hostname, bench_data) in enumerate(py_pivot_rows):
                data_points_py: list[float | None] = []
                for bench in bench_labels:
                    if bench in bench_data:
                        data_points_py.append(round(bench_data[bench]["mean"], 4))
                    else:
                        data_points_py.append(None)
                py_datasets.append(
                    {
                        "label": f"{py_label} ({hostname})",
                        "data": data_points_py,
                        "backgroundColor": _color_for(pidx) + "cc",
                        "borderColor": _color_for(pidx),
                        "borderWidth": 1,
                    }
                )
            datasets_json = json.dumps(py_datasets, indent=2)

            footnotes = _compute_footnotes(category, benchmarks, hostnames, hosts)
            table_html = _html_python_pivot_table(benchmarks, hostnames, footnotes, hosts)
            section = f"""
    <section id="cat-{category}">
      <h2>{title}</h2>
      <div class="chart-container">
        <canvas id="{canvas_id}"></canvas>
      </div>
      {table_html}
    </section>"""
            html_sections.append(section)

            chart_blocks.append(f"""
    CHARTS['{canvas_id}'] = new Chart(document.getElementById('{canvas_id}'), {{
      type: 'bar',
      data: {{
        labels: {labels_json},
        datasets: {datasets_json}
      }},
      options: {{
        responsive: true,
        plugins: {{
          legend: {{ display: true }},
          title: {{ display: true, text: '{title} (seconds, lower is better)' }}
        }},
        scales: {{
          y: {{ title: {{ display: true, text: 'Time (seconds)' }} }}
        }}
      }}
    }});""")
            continue

        if category in _OCTAVE_PIVOT_CATEGORIES:
            bench_labels, oct_pivot_rows = _build_octave_pivot(benchmarks, hostnames)
            labels_json = json.dumps(bench_labels)
            oct_datasets: list[dict[str, Any]] = []
            for oidx, (oct_label, hostname, bench_data) in enumerate(oct_pivot_rows):
                data_points_oct: list[float | None] = []
                for bench in bench_labels:
                    if bench in bench_data:
                        data_points_oct.append(round(bench_data[bench]["mean"], 4))
                    else:
                        data_points_oct.append(None)
                oct_datasets.append(
                    {
                        "label": f"{oct_label} ({hostname})",
                        "data": data_points_oct,
                        "backgroundColor": _color_for(oidx) + "cc",
                        "borderColor": _color_for(oidx),
                        "borderWidth": 1,
                    }
                )
            datasets_json = json.dumps(oct_datasets, indent=2)

            footnotes = _compute_footnotes(category, benchmarks, hostnames, hosts)
            table_html = _html_octave_pivot_table(benchmarks, hostnames, footnotes)
            section = f"""
    <section id="cat-{category}">
      <h2>{title}</h2>
      <div class="chart-container">
        <canvas id="{canvas_id}"></canvas>
      </div>
      {table_html}
    </section>"""
            html_sections.append(section)

            chart_blocks.append(f"""
    CHARTS['{canvas_id}'] = new Chart(document.getElementById('{canvas_id}'), {{
      type: 'bar',
      data: {{
        labels: {labels_json},
        datasets: {datasets_json}
      }},
      options: {{
        responsive: true,
        plugins: {{
          legend: {{ display: true }},
          title: {{ display: true, text: '{title} (seconds, lower is better)' }}
        }},
        scales: {{
          y: {{ title: {{ display: true, text: 'Time (seconds)' }} }}
        }}
      }}
    }});""")
            continue
        datasets: list[dict[str, Any]] = []
        for idx, hostname in enumerate(hostnames):
            data_points: list[float | None] = []
            error_bars: list[float | None] = []
            for bench_name in bench_names:
                if hostname in benchmarks.get(bench_name, {}):
                    r = benchmarks[bench_name][hostname]
                    data_points.append(round(r["mean"], 4))
                    error_bars.append(round(r["stddev"], 4))
                else:
                    data_points.append(None)
                    error_bars.append(None)
            datasets.append(
                {
                    "label": hostname,
                    "data": data_points,
                    "backgroundColor": _color_for(idx) + "cc",
                    "borderColor": _color_for(idx),
                    "borderWidth": 1,
                }
            )

        labels_json = json.dumps(bench_names)
        datasets_json = json.dumps(datasets, indent=2)

        # Detect if this category uses throughput metrics
        sample_bench_name = bench_names[0] if bench_names else None
        higher = False
        if sample_bench_name and hostnames:
            sample_r = benchmarks.get(sample_bench_name, {}).get(hostnames[0], {})
            higher = bool(sample_r.get("higher_is_better", False))

        y_label = "Throughput (KB/s)" if higher else "Time (seconds)"
        chart_title_suffix = "KB/s, higher is better" if higher else "seconds, lower is better"
        tooltip_suffix = "KB/s" if higher else "s"
        tooltip_digits = 2 if higher else 4
        higher_js = "true" if higher else "false"

        # Build HTML table for this category
        footnotes = _compute_footnotes(category, benchmarks, hostnames, hosts)
        cat_versions = _get_category_versions(category, all_host_features_html) or None
        table_html = _html_benchmark_table(
            benchmarks, bench_names, hostnames, footnotes, category, cat_versions
        )

        section = f"""
    <section id="cat-{category}">
      <h2>{title}</h2>
      <div class="chart-container">
        <canvas id="{canvas_id}"></canvas>
      </div>
      {table_html}
    </section>"""
        html_sections.append(section)

        chart_blocks.append(f"""
    CHARTS['{canvas_id}'] = new Chart(document.getElementById('{canvas_id}'), {{
      type: 'bar',
      data: {{
        labels: {labels_json},
        datasets: {datasets_json}
      }},
      options: {{
        higherIsBetter: {higher_js},
        responsive: true,
        plugins: {{
          title: {{ display: true, text: '{title} ({chart_title_suffix})' }},
          legend: {{ position: 'bottom' }},
          tooltip: {{
            callbacks: {{
              label: function(ctx) {{
                const v = ctx.parsed.y.toFixed({tooltip_digits});
                return ctx.dataset.label + ': ' + v + '{tooltip_suffix}';
              }}
            }}
          }}
        }},
        scales: {{
          y: {{
            beginAtZero: true,
            title: {{ display: true, text: '{y_label}' }}
          }}
        }}
      }}
    }});
    CHART_CATS['{canvas_id}'] = '{category}';""")

    # --- Navigation ---
    nav_items = []
    for category in sorted(table.keys()):
        title = CATEGORY_TITLES.get(category, category.replace("_", " ").title())
        nav_items.append(f'<a href="#cat-{category}">{title}</a>')

    # --- FFmpeg codec availability HTML ---
    codec_avail = _collect_codec_availability(hosts)
    codec_avail_html = ""
    if codec_avail:
        nav_items.append('<a href="#cat-codec-avail">Codec Availability</a>')
        avail_hosts = sorted(codec_avail.keys())
        ca_groups: list[str] = []
        for group_key, group_title in [
            ("video_encoders", "Video Encoders"),
            ("video_decoders", "Video Decoders"),
            ("audio_encoders", "Audio Encoders"),
            ("audio_decoders", "Audio Decoders"),
        ]:
            all_codecs: set[str] = set()
            for hdata in codec_avail.values():
                all_codecs.update(hdata.get(group_key, []))
            if not all_codecs:
                continue
            host_hdrs = "".join(f"<th>{h}</th>" for h in avail_hosts)
            ca_rows_html = ""
            for codec in sorted(all_codecs):
                cells = ""
                for h in avail_hosts:
                    available = codec in codec_avail[h].get(group_key, [])
                    if available:
                        badge = '<span style="color:#00e676">✓</span>'
                    else:
                        badge = '<span style="color:#888">—</span>'
                    cells += f"<td>{badge}</td>"
                ca_rows_html += f"          <tr><td><code>{codec}</code></td>{cells}</tr>\n"
            ca_groups.append(f"""
        <h3>{group_title}</h3>
        <table>
          <thead>
            <tr><th>Codec</th>{host_hdrs}</tr>
          </thead>
          <tbody>
{ca_rows_html}          </tbody>
        </table>""")
        codec_avail_html = f"""
    <section id="cat-codec-avail">
      <h2>FFmpeg Codec Availability</h2>
      {"".join(ca_groups)}
    </section>"""

    # --- Gentoo build times HTML ---
    build_time_data = _collect_build_times(hosts)
    build_times_html = ""
    if build_time_data:
        nav_items.append('<a href="#cat-build-times">Build Times</a>')
        bt_sections: list[str] = []
        for pkg_name in sorted(build_time_data.keys()):
            entries = sorted(
                build_time_data[pkg_name],
                key=lambda e: (e["host"], e["timestamp"]),
            )
            rows_html = ""
            for entry in entries:
                dur = entry["duration_secs"]
                dur_str = f"{dur // 60}m {dur % 60:02d}s"
                ts = entry.get("timestamp", 0)
                date_str = (
                    datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d") if ts > 0 else "—"
                )
                rows_html += f"""          <tr>
            <td>{entry["host"]}</td>
            <td>{entry["version"]}</td>
            <td>{date_str}</td>
            <td>{dur_str}</td>
            <td><code>{entry["kernel"]}</code></td>
            <td><code>{entry["compiler"]}</code></td>
          </tr>\n"""
            bt_sections.append(f"""
        <h3>{pkg_name}</h3>
        <table>
          <thead>
            <tr><th>Host</th><th>Version</th><th>Date</th><th>Duration</th>
                <th>Kernel</th><th>Compiler</th></tr>
          </thead>
          <tbody>
{rows_html}          </tbody>
        </table>""")
        build_times_html = f"""
    <section id="cat-build-times">
      <h2>Gentoo Package Build Times</h2>
      <p>Packages with longest build time &gt; 5 minutes.
         Last 3 builds shown with kernel and compiler at build time.</p>
      {"".join(bt_sections)}
    </section>"""

    # --- Boot times HTML ---
    boot_data_html = {h: hosts[h]["boot_times"] for h in hostnames if hosts[h].get("boot_times")}
    boot_times_html = ""
    if boot_data_html:
        nav_items.append('<a href="#cat-boot-times">Boot Times</a>')
        host_hdrs = "".join(f"<th>{h}</th>" for h in hostnames)
        boot_totals_html = {
            h: d["total_sec"]
            for h, d in boot_data_html.items()
            if d.get("available") and d.get("total_sec") is not None
        }
        fastest_boot_html = (  # noqa: F841  retained for potential future use
            min(boot_totals_html, key=boot_totals_html.__getitem__) if boot_totals_html else None
        )
        phase_rows_html = ""
        for phase_key, phase_label in [
            ("firmware_sec", "Firmware"),
            ("loader_sec", "Loader"),
            ("kernel_sec", "Kernel"),
            ("userspace_sec", "Userspace"),
            ("graphical_sec", "Graphical"),
            ("total_sec", "Total"),
        ]:
            cells = ""
            phase_vals = {
                h: d[phase_key]
                for h, d in boot_data_html.items()
                if d.get("available") and d.get(phase_key) is not None
            }
            fastest_phase = min(phase_vals, key=phase_vals.__getitem__) if phase_vals else None
            for hostname in hostnames:
                d = boot_data_html.get(hostname)
                val = d.get(phase_key) if d and d.get("available") else None
                if val is None:
                    cells += "<td>—</td>"
                elif hostname == fastest_phase:
                    cells += f"<td><strong>{val:.3f}</strong></td>"
                else:
                    cells += f"<td>{val:.3f}</td>"
            phase_rows_html += f"<tr><td>{phase_label}</td>{cells}</tr>\n"

        # Slowest services tables per host
        svc_sections_html = ""
        for hostname in hostnames:
            d = boot_data_html.get(hostname)
            services = (d.get("top_services") or []) if d and d.get("available") else []
            if not services:
                continue
            svc_rows_html = "".join(
                f"<tr><td><code>{s['name']}</code></td><td>{s['time_sec']:.3f}</td></tr>"
                for s in services[:10]
            )
            svc_sections_html += f"""
        <h3>{hostname}</h3>
        <table>
          <thead><tr><th>Service</th><th>Time (s)</th></tr></thead>
          <tbody>{svc_rows_html}</tbody>
        </table>"""

        boot_times_html = f"""
    <section id="cat-boot-times">
      <h2>System Boot Times</h2>
      <p>Measured at benchmark time. Times in seconds.
         <strong>Lowest</strong> per row is bold.<br>
         <code>systemd-analyze</code>: full phase breakdown + per-service blame. &nbsp;
         <code>dmesg</code>: kernel and early-userspace phases only
         (firmware/loader/graphical unavailable; service blame not available).</p>
      <table>
        <thead><tr><th>Phase</th>{host_hdrs}</tr></thead>
        <tbody>
          <tr><td>Method</td>{
            "".join(
                f"<td><code>{boot_data_html.get(h, {}).get('method', '—')}</code></td>"
                for h in hostnames
            )
        }</tr>
{phase_rows_html}        </tbody>
      </table>
      {"<h3>Slowest Services at Boot</h3>" + svc_sections_html if svc_sections_html else ""}
    </section>"""

    nav_html = " · ".join(nav_items)

    charts_js = "\n".join(chart_blocks)

    # Serialize embedded data for JS filtering
    host_meta_js = json.dumps(host_meta_for_js)
    bench_data_js = json.dumps(bench_data_for_js)
    host_order_js = json.dumps(hostnames)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Gentoo VM Benchmark Report</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
  <style>
    :root {{
      --bg: #1a1a2e;
      --surface: #16213e;
      --text: #e0e0e0;
      --accent: #0f3460;
      --highlight: #e94560;
      --border: #333;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      display: flex;
      align-items: flex-start;
      min-height: 100vh;
    }}
    h1 {{
      text-align: center;
      color: var(--highlight);
      margin-bottom: 0.5rem;
      font-size: 2rem;
    }}
    .timestamp {{
      text-align: center;
      color: #888;
      margin-bottom: 2rem;
    }}
    nav {{
      text-align: center;
      margin-bottom: 2rem;
      padding: 1rem;
      background: var(--surface);
      border-radius: 8px;
    }}
    nav a {{
      color: #4dc9f6;
      text-decoration: none;
      padding: 0.3rem 0.6rem;
    }}
    nav a:hover {{ text-decoration: underline; }}
    section {{
      background: var(--surface);
      border-radius: 8px;
      padding: 1.5rem;
      margin-bottom: 2rem;
    }}
    h2 {{
      color: #4dc9f6;
      margin-bottom: 1rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.5rem;
    }}
    .chart-container {{
      position: relative;
      height: 400px;
      margin-bottom: 1.5rem;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 1rem;
      font-size: 0.85rem;
    }}
    th, td {{
      padding: 0.5rem 0.75rem;
      text-align: left;
      border-bottom: 1px solid var(--border);
    }}
    th {{
      background: var(--accent);
      color: #fff;
      position: sticky;
      top: 0;
    }}
    tr:hover {{ background: rgba(255,255,255,0.03); }}
    .fastest {{ color: #00e676; font-weight: bold; }}
    .host-summary {{ overflow-x: auto; }}
    .host-summary table {{ font-size: 0.8rem; }}
    .bench-footnote {{
      font-size: 0.82em;
      color: #aaa;
      margin-top: 0.25em;
      font-style: italic;
    }}
    .version-row td, .version-row th {{
      font-size: 0.8em;
      color: #aaa;
      font-style: italic;
      background: rgba(255,255,255,0.02);
    }}
    /* Filter sidebar */
    #filter-sidebar {{
      width: 220px;
      min-width: 180px;
      flex-shrink: 0;
      background: var(--surface);
      padding: 1.2rem;
      height: 100vh;
      overflow-y: auto;
      position: sticky;
      top: 0;
      border-right: 1px solid var(--border);
    }}
    #filter-sidebar h3 {{
      color: var(--highlight);
      font-size: 1rem;
      margin-bottom: 0.8rem;
    }}
    #main-content {{
      flex: 1;
      padding: 2rem;
      overflow-x: hidden;
      min-width: 0;
    }}
    .filter-section-label {{
      color: #4dc9f6;
      font-size: 0.72rem;
      font-weight: bold;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin: 1rem 0 0.35rem;
      display: block;
    }}
    .filter-group-header {{
      color: #4dc9f6;
      font-size: 0.78rem;
      font-weight: bold;
      margin: 0.7rem 0 0.25rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .filter-host-label {{
      display: flex;
      align-items: center;
      gap: 0.35rem;
      font-size: 0.8rem;
      padding: 0.12rem 0;
      cursor: pointer;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .filter-host-label:hover {{ color: #fff; }}
    .filter-btn-row {{ display: flex; gap: 0.4rem; margin-bottom: 0.6rem; flex-wrap: wrap; }}
    .btn-sm {{
      background: var(--accent);
      color: #e0e0e0;
      border: none;
      padding: 0.22rem 0.55rem;
      border-radius: 4px;
      cursor: pointer;
      font-size: 0.75rem;
    }}
    .btn-sm:hover {{ background: #1a4a80; }}
    .filter-divider {{ border: none; border-top: 1px solid var(--border); margin: 0.75rem 0; }}
    .filter-toggle-label {{
      display: flex;
      align-items: center;
      gap: 0.45rem;
      font-size: 0.82rem;
      cursor: pointer;
      margin-bottom: 0.4rem;
    }}
    @media (max-width: 900px) {{
      body {{ flex-direction: column; }}
      #filter-sidebar {{
        width: 100%;
        height: auto;
        position: static;
        border-right: none;
        border-bottom: 1px solid var(--border);
      }}
      .chart-container {{ height: 300px; }}
    }}
  </style>
</head>
<body>
  <!-- Filter sidebar -->
  <aside id="filter-sidebar">
    <h3>🔍 Filters</h3>
    <div class="filter-btn-row">
      <button class="btn-sm" onclick="selectAllHosts()">All</button>
      <button class="btn-sm" onclick="clearAllHosts()">None</button>
    </div>
    <div id="host-filter-groups"><!-- filled by buildFilterPanel() --></div>
    <hr class="filter-divider">
    <label class="filter-toggle-label">
      <input type="checkbox" id="normalize-toggle" onchange="applyFilters()">
      Normalize (÷ fastest)
    </label>
    <label class="filter-toggle-label">
      <input type="checkbox" id="horiz-toggle" onchange="applyFilters()">
      Horizontal bars
    </label>
  </aside>

  <!-- Main content -->
  <div id="main-content">
  <h1>🖥️ Gentoo VM Benchmark Report</h1>
  <p class="timestamp">Generated: {timestamp}</p>

  <nav>{nav_html}</nav>

  <section>
    <h2>Host Configuration Summary</h2>
    <div class="host-summary">
      {summary_html}
    </div>
  </section>

  {"".join(html_sections)}

  {codec_avail_html}

  {build_times_html}

  {boot_times_html}

  </div><!-- #main-content -->

  <script>
    // All benchmark data embedded for client-side filtering
    const HOST_META = {host_meta_js};
    const BENCH_DATA = {bench_data_js};
    const HOST_ORDER = {host_order_js};

    // Chart registry (canvas_id → Chart instance, populated below)
    const CHARTS = {{}};
    const CHART_CATS = {{}};

    // Build sidebar filter panel dynamically from HOST_META
    function buildFilterPanel() {{
      const byOS = {{}};
      for (const [host, meta] of Object.entries(HOST_META)) {{
        const os = meta.os_family || 'Unknown';
        if (!byOS[os]) byOS[os] = [];
        byOS[os].push(host);
      }}
      const container = document.getElementById('host-filter-groups');
      for (const os of Object.keys(byOS).sort()) {{
        const div = document.createElement('div');
        let inner = `<div class="filter-group-header">${{os}}</div>`;
        for (const host of byOS[os].sort()) {{
          inner += `<label class="filter-host-label">
            <input type="checkbox" data-host="${{host}}" checked onchange="applyFilters()">
            ${{host}}
          </label>`;
        }}
        div.innerHTML = inner;
        container.appendChild(div);
      }}
    }}

    function getSelectedHosts() {{
      const sel = new Set();
      document.querySelectorAll('#host-filter-groups input[data-host]:checked')
        .forEach(cb => sel.add(cb.dataset.host));
      return sel;
    }}

    function selectAllHosts() {{
      document.querySelectorAll('#host-filter-groups input[data-host]')
        .forEach(cb => {{ cb.checked = true; }});
      applyFilters();
    }}

    function clearAllHosts() {{
      document.querySelectorAll('#host-filter-groups input[data-host]')
        .forEach(cb => {{ cb.checked = false; }});
      applyFilters();
    }}

    // Re-render all charts based on current filter state
    function applyFilters() {{
      const selected = getSelectedHosts();
      const normalize = document.getElementById('normalize-toggle').checked;
      const horiz = document.getElementById('horiz-toggle').checked;

      for (const [canvasId, chart] of Object.entries(CHARTS)) {{
        const category = CHART_CATS[canvasId];
        const catData = BENCH_DATA[category] || {{}};
        const benchNames = chart.data.labels;

        chart.data.datasets.forEach((dataset, idx) => {{
          const hostname = HOST_ORDER[idx];
          chart.setDatasetVisibility(idx, selected.has(hostname));

          // Recompute data points from embedded BENCH_DATA
          dataset.data = benchNames.map(bench => {{
            const val = catData[bench]?.[hostname]?.mean;
            if (val == null) return null;
            if (normalize) {{
              const allVals = Object.entries(catData[bench] || {{}})
                .filter(([h]) => selected.has(h))
                .map(([, r]) => r.mean)
                .filter(v => v > 0);
              const hib = chart.options.higherIsBetter || false;
              const refVal = hib ? Math.max(...allVals) : Math.min(...allVals);
              return refVal > 0 ? parseFloat((hib ? val / refVal : refVal / val).toFixed(4)) : null;
            }}
            return val;
          }});

          // Update tooltip suffix
          dataset.tooltip_suffix = normalize ? 'x' : (chart.options.higherIsBetter ? 'KB/s' : 's');
        }});

        // Toggle orientation
        chart.options.indexAxis = horiz ? 'y' : 'x';

        // Update axis labels
        const hib = chart.options.higherIsBetter || false;
        const valueLabel = normalize
          ? (hib ? 'Relative to best (1.0 = best)' : 'Relative to fastest (1.0 = fastest)')
          : (hib ? 'Throughput (KB/s)' : 'Time (seconds)');
        const catTitle = chart.options.plugins.title.text
          .replace(/ \\(.*\\)$/, '')
          + (normalize
            ? (hib ? ' (normalized, higher is better)' : ' (normalized, lower is better)')
            : (hib ? ' (KB/s, higher is better)' : ' (seconds, lower is better)'));
        chart.options.plugins.title.text = catTitle;
        if (horiz) {{
          chart.options.scales.x = chart.options.scales.x || {{}};
          chart.options.scales.x.title = {{ display: true, text: valueLabel }};
          chart.options.scales.y = chart.options.scales.y || {{}};
          delete chart.options.scales.y.title;
        }} else {{
          chart.options.scales.y = chart.options.scales.y || {{}};
          chart.options.scales.y.title = {{ display: true, text: valueLabel }};
          chart.options.scales.x = chart.options.scales.x || {{}};
          delete chart.options.scales.x.title;
        }}

        chart.update();
      }}
    }}

    document.addEventListener('DOMContentLoaded', buildFilterPanel);

    // Chart.js defaults
    Chart.defaults.color = '#e0e0e0';
    Chart.defaults.borderColor = '#333';
    {charts_js}
  </script>
</body>
</html>"""

    return html


def _html_runtime_env_rows(hosts: dict[str, dict[str, Any]], hostnames: list[str]) -> str:
    """Build HTML <tr> rows for the runtime environment table."""
    rows: list[str] = []
    for hostname in hostnames:
        meta = hosts[hostname].get("metadata", {})
        feat = extract_features(meta)
        smt_cell = {"yes": "✓", "no": "✗"}.get(feat.get("smt", "—"), "—")
        mit = feat.get("mitigations", "default")
        mit_style = ' style="color:#ff5252"' if mit == "off" else ""
        flags = feat.get("cpu_flags_x86", "—")
        flags_cell = f'<code title="{flags}">{flags[:40]}{"…" if len(flags) > 40 else ""}</code>'
        hv_badge = _HV_BADGE if feat.get("is_hypervisor") else ""
        rows.append(f"""      <tr>
        <td><strong>{hostname}</strong>{hv_badge}</td>
        <td>{feat.get("virt_type", "—")}</td>
        <td>{feat.get("cpu_governor", "—")}</td>
        <td>{smt_cell}</td>
        <td>{feat.get("thp", "—")}</td>
        <td{mit_style}>{mit}</td>
        <td>{feat.get("preempt_model", "—")}</td>
        <td>{feat.get("io_scheduler", "—")}</td>
        <td>{feat.get("numa_nodes", "—")}</td>
        <td>{feat.get("mem_speed", "—")}</td>
        <td>{feat.get("cpu_cache_l3", "—")}</td>
        <td>{flags_cell}</td>
      </tr>""")
    return "\n".join(rows)


def _html_host_summary(
    hosts: dict[str, dict[str, Any]],
    hostnames: list[str],
    scores: dict[str, float] | None = None,
) -> str:
    """Build an HTML summary table of host configurations."""
    rows: list[str] = []
    for rank, hostname in enumerate(hostnames, 1):
        meta = hosts[hostname].get("metadata", {})
        feat = extract_features(meta)
        lto_badge = {
            "yes": '<span style="color:#00e676">✓ full</span>',
            "thin": '<span style="color:#4dc9f6">✓ thin</span>',
            "no": '<span style="color:#888">✗</span>',
        }.get(feat.get("lto", "no"), "?")
        hv_badge = _HV_BADGE if feat.get("is_hypervisor") else ""
        swap_s = feat.get("swap", "—")
        swap_cell = "✓" if swap_s == "yes" else "✗" if swap_s == "no" else "—"

        if scores and hostname in scores:
            score_cell = _score_badge_html(scores[hostname], rank)
            rank_cell = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")
        else:
            score_cell = "—"
            rank_cell = "—"

        rows.append(f"""      <tr>
        <td style="text-align:center">{rank_cell}</td>
        <td><strong>{hostname}</strong>{hv_badge}</td>
        <td style="text-align:right">{score_cell}</td>
        <td>{feat.get("kernel", "—")}</td>
        <td>{feat.get("cpu_model", "?")}</td>
        <td>{feat.get("cpu_clock", "—")}</td>
        <td>{feat.get("cpu_cores", "?")}</td>
        <td><code>{feat.get("opt_level", "?")}</code></td>
        <td><code>{feat.get("march", "?")}</code></td>
        <td><code>{feat.get("march_native", "—")}</code></td>
        <td>{lto_badge}</td>
        <td>{feat.get("hardening", "—")}</td>
        <td>{feat.get("scheduler", "—")}</td>
        <td>{feat.get("filesystem", "—")}</td>
        <td>{swap_cell}</td>
        <td>{feat.get("calibration_mips", "—")}</td>
        <td>{feat.get("passmark_st", "—")}</td>
        <td>{feat.get("passmark_mt", "—")}</td>
        <td>{feat.get("ver_gcc", "—")}</td>
        <td>{feat.get("ver_clang", "—")}</td>
        <td>{feat.get("ver_rustc", "—")}</td>
        <td>{feat.get("ver_python", "—")}</td>
        <td><code>{feat.get("libc", "—")}</code></td>
        <td>{feat.get("gcc_config", "—")}</td>
        <td><code>{feat.get("makeflags", "—")}</code></td>
        <td>{feat.get("parallel_jobs", "—")}</td>
      </tr>""")

    return f"""    <h3>Host Configuration Summary</h3>
    <p style="font-size:0.85em;color:#aaa">Score = weighted geometric mean of per-benchmark
    relative performance (fastest host per benchmark = 100).
    See <code>scripts/scoring_weights.yml</code> to customise category weights.</p>
    <table>
      <thead>
        <tr>
          <th>#</th><th>Host</th><th>Score</th><th>Kernel</th><th>CPU</th>
          <th>Clock</th><th>Cores</th><th>Opt</th>
          <th>March</th><th>March (native)</th><th>LTO</th><th>Hardening</th>
          <th>Scheduler</th><th>Filesystem</th><th>Swap</th>
          <th>7z MIPS</th><th>PassMark (ST)</th><th>PassMark (MT)</th>
          <th>GCC</th><th>Clang</th><th>Rust</th><th>Python</th>
          <th>libc</th><th>GCC defaults</th><th>MAKEFLAGS</th><th>Parallel jobs</th>
        </tr>
      </thead>
      <tbody>
{"".join(rows)}
      </tbody>
    </table>
    <h3>Host Runtime Environment</h3>
    <table>
      <thead>
        <tr>
          <th>Host</th><th>Virt</th><th>Governor</th><th>SMT</th><th>THP</th>
          <th>Mitigations</th><th>Preempt</th><th>I/O Sched</th><th>NUMA</th>
          <th>Mem Speed</th><th>L3 Cache</th><th>CPU_FLAGS_X86</th>
        </tr>
      </thead>
      <tbody>
{_html_runtime_env_rows(hosts, hostnames)}
      </tbody>
    </table>"""


def _html_benchmark_table(
    benchmarks: dict[str, dict[str, dict[str, float]]],
    bench_names: list[str],
    hostnames: list[str],
    footnotes: dict[str, list[str]] | None = None,
    category: str = "",
    category_versions: dict[str, str] | None = None,
) -> str:
    """Build an HTML table for a single benchmark category."""
    header_cells = "".join(f"<th>{h}</th>" for h in hostnames)
    rows: list[str] = []

    # Optional version row at top of table
    if category_versions:
        ver_cells = "".join(f"<td>{category_versions.get(h, '—')}</td>" for h in hostnames)
        rows.append(f'        <tr class="version-row"><th>Tool version</th>{ver_cells}</tr>')

    for bench_name in bench_names:
        host_results = benchmarks.get(bench_name, {})
        higher = _is_higher_better(host_results)
        means = {h: r["mean"] for h, r in host_results.items() if r["mean"] > 0}
        fastest = (max if higher else min)(means, key=means.get) if means else None
        display_label = _format_bench_label(bench_name, category)

        cells: list[str] = [f"<td><strong>{display_label}</strong></td>"]
        for hostname in hostnames:
            if hostname in host_results:
                r = host_results[hostname]
                if higher:
                    val = _format_throughput(r["mean"], r["stddev"])
                else:
                    val = f"{r['mean']:.4f} ± {r['stddev']:.4f}"
                cls = ' class="fastest"' if hostname == fastest else ""
                cells.append(f"<td{cls}>{val}</td>")
            else:
                cells.append("<td>—</td>")

        rows.append("        <tr>" + "".join(cells) + "</tr>")

    footnote_html = ""
    if footnotes:
        parts = []
        for hostname in hostnames:
            if hostname in footnotes:
                reasons = "; ".join(footnotes[hostname])
                parts.append(f"<strong>{hostname}</strong>: {reasons}")
        if parts:
            footnote_html = (
                f'\n    <p class="bench-footnote">Missing results — {" · ".join(parts)}</p>'
            )

    return (
        f"""    <table>
      <thead>
        <tr><th>Benchmark</th>{header_cells}</tr>
      </thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table>"""
        + footnote_html
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate benchmark reports from hyperfine JSON results.",
    )
    parser.add_argument(
        "benchmarks_dir",
        type=Path,
        help="Directory containing results/<host>/*.json",
    )
    parser.add_argument(
        "--anonymize",
        action="store_true",
        help="Replace hostnames with Greek mythology names",
    )
    parser.add_argument(
        "--weights",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "YAML file with category scoring weights "
            "(default: benchmarks/scoring_weights.yml if present)"
        ),
    )
    args = parser.parse_args()

    base_dir: Path = args.benchmarks_dir
    hosts = load_results(base_dir)

    if not hosts:
        print("ERROR: no host results found", file=sys.stderr)
        sys.exit(1)

    if args.anonymize:
        hosts = anonymize_hosts(hosts)
        print("Anonymized hostnames with Greek mythology names")

    print(f"Found results for {len(hosts)} hosts: {', '.join(sorted(hosts))}")

    table = build_comparison_table(hosts)

    # Load scoring weights and compute scores
    weights_path = args.weights or (base_dir / "scoring_weights.yml")
    # Also check next to the script itself as a fallback
    if not weights_path.exists():
        weights_path = Path(__file__).parent / "scoring_weights.yml"
    weights = load_scoring_weights(weights_path)
    scores = compute_scores(table, weights)
    if scores:
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        print("Scores (weighted, 0–100):")
        for rank, (h, s) in enumerate(ranked, 1):
            print(f"  {rank:2}. {h}: {s:.1f}")

    # Markdown report
    md = generate_markdown(hosts, table, scores)
    md_path = base_dir / "report.md"
    md_path.write_text(md)
    print(f"Markdown report: {md_path}")

    # HTML report
    html = generate_html(hosts, table, scores)
    html_path = base_dir / "report.html"
    html_path.write_text(html)
    print(f"HTML report: {html_path}")


if __name__ == "__main__":
    main()
