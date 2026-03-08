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
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Chart.js colors — one per host, cycling if >16 hosts
CHART_COLORS = [
    "#4dc9f6", "#f67019", "#f53794", "#537bc4",
    "#acc236", "#166a8f", "#00a950", "#58595b",
    "#8549ba", "#e6194b", "#3cb44b", "#ffe119",
    "#4363d8", "#f58231", "#911eb4", "#42d4f4",
]

CATEGORY_TITLES = {
    "compression": "Compression",
    "crypto_symmetric": "Cryptography — Symmetric Ciphers",
    "crypto_hash": "Cryptography — Digests (OpenSSL)",
    "crypto_hash_coreutils": "Cryptography — Digests (Coreutils)",
    "crypto_openssl_speed": "OpenSSL Speed — Symmetric & AEAD Throughput",
    "crypto_asymmetric": "Cryptography — Asymmetric / Public Key",
    "crypto_hmac": "Cryptography — HMAC",
    "crypto_kdf": "Cryptography — Key Derivation",
    "crypto_gpg": "GPG Sign / Verify",
    "crypto_aes": "Cryptography — AES (legacy)",
    "compiler_c_compile": "C Compilation Speed",
    "compiler_c_runtime": "C Runtime Performance",
    "compiler_rust": "Rust Compilation Speed",
    "compiler_go": "Go Compilation Speed",
    "python": "Python Performance",
    "ffmpeg_video_encode": "FFmpeg Video Encoding",
    "ffmpeg_video_decode": "FFmpeg Video Decoding",
    "ffmpeg_audio": "FFmpeg Audio Encoding",
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
}

# Greek mythology names for host anonymization (deterministic order)
_GREEK_NAMES = [
    "Zeus", "Hera", "Poseidon", "Demeter", "Athena", "Apollo",
    "Artemis", "Ares", "Aphrodite", "Hephaestus", "Hermes", "Hestia",
    "Dionysus", "Persephone", "Hades", "Prometheus", "Achilles",
    "Odysseus", "Heracles", "Perseus", "Theseus", "Orpheus",
    "Icarus", "Minos", "Medea", "Cassandra", "Electra", "Antigone",
    "Andromeda", "Atalanta", "Calypso", "Circe", "Daphne", "Echo",
    "Eurydice", "Galatea", "Hecate", "Iris", "Penelope", "Selene",
    "Pandora", "Psyche", "Ariadne", "Phaedra", "Niobe", "Io",
    "Thetis", "Nemesis", "Tyche", "Nike",
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


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


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
            with open(json_file) as f:
                data = json.load(f)
            if "results" in data:
                hosts[hostname]["benchmarks"][category] = data["results"]
            elif "packages" in data:
                # Gentoo build time data
                hosts[hostname]["gentoo_build_times"] = data["packages"]
            elif "video_encoders" in data:
                # FFmpeg codec availability
                hosts[hostname]["ffmpeg_codecs"] = data

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
        features["swap"] = "yes" if swap_val.lower() in ("true", "yes", "enabled") else "no" if swap_val else "—"
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

    return features


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a Markdown table with alignment."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))

    sep = "| " + " | ".join("-" * w for w in widths) + " |"
    hdr = "| " + " | ".join(h.ljust(w) for h, w in zip(headers, widths)) + " |"
    lines = [hdr, sep]
    for row in rows:
        padded = [
            cell.ljust(widths[i]) if i < len(widths) else cell
            for i, cell in enumerate(row)
        ]
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
                result[pkg_name].append({
                    "host": hostname,
                    "version": build.get("version", "?"),
                    "duration_secs": build.get("duration_secs", 0),
                    "kernel": build.get("kernel", "unknown"),
                    "compiler": build.get("compiler", "unknown"),
                    "timestamp": build.get("timestamp", 0),
                })
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


def generate_markdown(
    hosts: dict[str, dict[str, Any]],
    table: dict[str, dict[str, dict[str, dict[str, float]]]],
) -> str:
    """Generate the full Markdown report."""
    lines: list[str] = []
    hostnames = sorted(hosts.keys())
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines.append("# Gentoo VM Benchmark Report")
    lines.append("")
    lines.append(f"*Generated: {timestamp}*")
    lines.append("")

    # --- Host summary table ---
    lines.append("## Host Configuration Summary")
    lines.append("")

    summary_headers = [
        "Host", "OS", "Kernel", "CPU", "Clock", "Cores", "Opt", "March",
        "March (native)", "LTO", "Hardening", "Scheduler", "Filesystem",
        "Swap", "7z MIPS", "PassMark (ST)", "PassMark (MT)", "GCC", "Clang",
    ]
    summary_rows: list[list[str]] = []
    for hostname in hostnames:
        meta = hosts[hostname].get("metadata", {})
        feat = extract_features(meta)
        os_label = feat.get("os", "?")
        if feat.get("os_version", "—") != "—":
            os_label += " " + feat["os_version"]
        hv_prefix = "[HV] " if feat.get("is_hypervisor") else ""
        summary_rows.append([
            hv_prefix + hostname,
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
        ])
    lines.append(_md_table(summary_headers, summary_rows))
    lines.append("")

    # --- Runtime environment table ---
    lines.append("## Host Runtime Environment")
    lines.append("")
    env_headers = [
        "Host", "Virt", "Governor", "SMT", "THP", "Mitigations",
        "Preempt", "I/O Sched", "NUMA", "Mem Speed", "L3 Cache", "CPU_FLAGS_X86",
    ]
    env_rows: list[list[str]] = []
    for hostname in hostnames:
        meta = hosts[hostname].get("metadata", {})
        feat = extract_features(meta)
        hv_prefix = "[HV] " if feat.get("is_hypervisor") else ""
        env_rows.append([
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
        ])
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
    for category in sorted(table.keys()):
        title = CATEGORY_TITLES.get(category, category.replace("_", " ").title())
        benchmarks = table[category]
        lines.append(f"## {title}")
        lines.append("")
        lines.append("Times in seconds (mean ± stddev). **Lowest** is bold.")
        lines.append("")

        headers = ["Benchmark"] + hostnames
        rows: list[list[str]] = []

        for bench_name in sorted(benchmarks.keys()):
            host_results = benchmarks[bench_name]
            row = [bench_name]

            # Find the fastest host for this benchmark
            means = {
                h: r["mean"]
                for h, r in host_results.items()
                if r["mean"] > 0
            }
            fastest = min(means, key=means.get) if means else None

            for hostname in hostnames:
                if hostname in host_results:
                    r = host_results[hostname]
                    cell = f"{r['mean']:.3f} ± {r['stddev']:.3f}"
                    if hostname == fastest:
                        cell = f"**{cell}**"
                else:
                    cell = "—"
                row.append(cell)

            rows.append(row)

        lines.append(_md_table(headers, rows))
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
                    datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                    if ts > 0
                    else "—"
                )
                bt_rows.append([
                    entry["host"],
                    entry["version"],
                    date_str,
                    dur_str,
                    entry["kernel"],
                    entry["compiler"],
                ])
            lines.append(_md_table(bt_headers, bt_rows))
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------


def _color_for(idx: int) -> str:
    return CHART_COLORS[idx % len(CHART_COLORS)]


def generate_html(
    hosts: dict[str, dict[str, Any]],
    table: dict[str, dict[str, dict[str, dict[str, float]]]],
) -> str:
    """Generate an interactive HTML report with Chart.js."""
    hostnames = sorted(hosts.keys())
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Pre-build Chart.js datasets per category
    chart_blocks: list[str] = []
    chart_id = 0

    html_sections: list[str] = []

    # --- Host summary ---
    summary_html = _html_host_summary(hosts, hostnames)

    # --- Per-category sections ---
    for category in sorted(table.keys()):
        title = CATEGORY_TITLES.get(category, category.replace("_", " ").title())
        benchmarks = table[category]
        bench_names = sorted(benchmarks.keys())
        chart_id += 1
        canvas_id = f"chart_{chart_id}"

        # Build datasets JSON
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
            datasets.append({
                "label": hostname,
                "data": data_points,
                "backgroundColor": _color_for(idx) + "cc",
                "borderColor": _color_for(idx),
                "borderWidth": 1,
            })

        labels_json = json.dumps(bench_names)
        datasets_json = json.dumps(datasets, indent=2)

        # Build HTML table for this category
        table_html = _html_benchmark_table(benchmarks, bench_names, hostnames)

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
    new Chart(document.getElementById('{canvas_id}'), {{
      type: 'bar',
      data: {{
        labels: {labels_json},
        datasets: {datasets_json}
      }},
      options: {{
        responsive: true,
        plugins: {{
          title: {{ display: true, text: '{title} (seconds, lower is better)' }},
          legend: {{ position: 'bottom' }},
          tooltip: {{
            callbacks: {{
              label: function(ctx) {{
                return ctx.dataset.label + ': ' + ctx.parsed.y.toFixed(4) + 's';
              }}
            }}
          }}
        }},
        scales: {{
          y: {{
            beginAtZero: true,
            title: {{ display: true, text: 'Time (seconds)' }}
          }}
        }}
      }}
    }});""")

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
                    badge = '<span style="color:#00e676">✓</span>' if available else '<span style="color:#888">—</span>'
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
                    datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                    if ts > 0
                    else "—"
                )
                rows_html += f"""          <tr>
            <td>{entry['host']}</td>
            <td>{entry['version']}</td>
            <td>{date_str}</td>
            <td>{dur_str}</td>
            <td><code>{entry['kernel']}</code></td>
            <td><code>{entry['compiler']}</code></td>
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

    nav_html = " · ".join(nav_items)

    charts_js = "\n".join(chart_blocks)

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
      padding: 2rem;
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
    @media (max-width: 768px) {{
      body {{ padding: 0.5rem; }}
      .chart-container {{ height: 300px; }}
    }}
  </style>
</head>
<body>
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

  <script>
    Chart.defaults.color = '#e0e0e0';
    Chart.defaults.borderColor = '#333';
    {charts_js}
  </script>
</body>
</html>"""

    return html


def _html_runtime_env_rows(
    hosts: dict[str, dict[str, Any]], hostnames: list[str]
) -> str:
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
        hv_badge = ' <span style="background:#5c4200;color:#ffd600;font-size:0.75em;padding:1px 5px;border-radius:3px;vertical-align:middle">HV</span>' if feat.get("is_hypervisor") else ""
        rows.append(f"""      <tr>
        <td><strong>{hostname}</strong>{hv_badge}</td>
        <td>{feat.get('virt_type', '—')}</td>
        <td>{feat.get('cpu_governor', '—')}</td>
        <td>{smt_cell}</td>
        <td>{feat.get('thp', '—')}</td>
        <td{mit_style}>{mit}</td>
        <td>{feat.get('preempt_model', '—')}</td>
        <td>{feat.get('io_scheduler', '—')}</td>
        <td>{feat.get('numa_nodes', '—')}</td>
        <td>{feat.get('mem_speed', '—')}</td>
        <td>{feat.get('cpu_cache_l3', '—')}</td>
        <td>{flags_cell}</td>
      </tr>""")
    return "\n".join(rows)


def _html_host_summary(
    hosts: dict[str, dict[str, Any]], hostnames: list[str]
) -> str:
    """Build an HTML summary table of host configurations."""
    rows: list[str] = []
    for hostname in hostnames:
        meta = hosts[hostname].get("metadata", {})
        feat = extract_features(meta)
        lto_badge = {
            "yes": '<span style="color:#00e676">✓ full</span>',
            "thin": '<span style="color:#4dc9f6">✓ thin</span>',
            "no": '<span style="color:#888">✗</span>',
        }.get(feat.get("lto", "no"), "?")
        hv_badge = ' <span style="background:#5c4200;color:#ffd600;font-size:0.75em;padding:1px 5px;border-radius:3px;vertical-align:middle">HV</span>' if feat.get("is_hypervisor") else ""

        rows.append(f"""      <tr>
        <td><strong>{hostname}</strong>{hv_badge}</td>
        <td>{feat.get('kernel', '—')}</td>
        <td>{feat.get('cpu_model', '?')}</td>
        <td>{feat.get('cpu_clock', '—')}</td>
        <td>{feat.get('cpu_cores', '?')}</td>
        <td><code>{feat.get('opt_level', '?')}</code></td>
        <td><code>{feat.get('march', '?')}</code></td>
        <td><code>{feat.get('march_native', '—')}</code></td>
        <td>{lto_badge}</td>
        <td>{feat.get('hardening', '—')}</td>
        <td>{feat.get('scheduler', '—')}</td>
        <td>{feat.get('filesystem', '—')}</td>
        <td>{'✓' if feat.get('swap', '—') == 'yes' else '✗' if feat.get('swap', '—') == 'no' else '—'}</td>
        <td>{feat.get('calibration_mips', '—')}</td>
        <td>{feat.get('passmark_st', '—')}</td>
        <td>{feat.get('passmark_mt', '—')}</td>
        <td>{feat.get('ver_gcc', '—')}</td>
        <td>{feat.get('ver_clang', '—')}</td>
        <td>{feat.get('ver_rustc', '—')}</td>
        <td>{feat.get('ver_python', '—')}</td>
      </tr>""")

    return f"""    <h3>Host Configuration Summary</h3>
    <table>
      <thead>
        <tr>
          <th>Host</th><th>Kernel</th><th>CPU</th><th>Clock</th><th>Cores</th><th>Opt</th>
          <th>March</th><th>March (native)</th><th>LTO</th><th>Hardening</th>
          <th>Scheduler</th><th>Filesystem</th><th>Swap</th>
          <th>7z MIPS</th><th>PassMark (ST)</th><th>PassMark (MT)</th>
          <th>GCC</th><th>Clang</th><th>Rust</th><th>Python</th>
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
) -> str:
    """Build an HTML table for a single benchmark category."""
    header_cells = "".join(f"<th>{h}</th>" for h in hostnames)
    rows: list[str] = []

    for bench_name in bench_names:
        host_results = benchmarks.get(bench_name, {})
        means = {
            h: r["mean"] for h, r in host_results.items() if r["mean"] > 0
        }
        fastest = min(means, key=means.get) if means else None

        cells: list[str] = [f"<td><strong>{bench_name}</strong></td>"]
        for hostname in hostnames:
            if hostname in host_results:
                r = host_results[hostname]
                val = f"{r['mean']:.4f} ± {r['stddev']:.4f}"
                cls = ' class="fastest"' if hostname == fastest else ""
                cells.append(f"<td{cls}>{val}</td>")
            else:
                cells.append("<td>—</td>")

        rows.append("        <tr>" + "".join(cells) + "</tr>")

    return f"""    <table>
      <thead>
        <tr><th>Benchmark</th>{header_cells}</tr>
      </thead>
      <tbody>
{chr(10).join(rows)}
      </tbody>
    </table>"""


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

    # Markdown report
    md = generate_markdown(hosts, table)
    md_path = base_dir / "report.md"
    md_path.write_text(md)
    print(f"Markdown report: {md_path}")

    # HTML report
    html = generate_html(hosts, table)
    html_path = base_dir / "report.html"
    html_path.write_text(html)
    print(f"HTML report: {html_path}")


if __name__ == "__main__":
    main()
