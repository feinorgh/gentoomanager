"""Tests for the benchmark report generator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make scripts importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from generate_benchmark_report import (
    anonymize_hosts,
    build_comparison_table,
    extract_features,
    generate_html,
    generate_markdown,
    load_results,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_hyperfine_json(*benchmarks: tuple[str, float, float]) -> dict:
    """Create a hyperfine-style JSON result."""
    return {
        "results": [
            {
                "command": name,
                "mean": mean,
                "stddev": stddev,
                "min": mean - stddev,
                "max": mean + stddev,
                "median": mean,
                "times": [mean] * 3,
            }
            for name, mean, stddev in benchmarks
        ]
    }


def _make_metadata(
    hostname: str,
    common_flags: str = "-O2 -march=native -pipe",
    cflags: str = "${COMMON_FLAGS}",
    ldflags: str = "",
) -> dict:
    return {
        "hostname": hostname,
        "cpu_model": "Intel Xeon E5-2680 v4",
        "cpu_cores": 4,
        "versions": [
            "gcc=gcc (Gentoo 13.3.0) 13.3.0",
            "clang=clang version 17.0.6",
            "rustc=rustc 1.75.0",
            "python=Python 3.12.1",
            "go=go version go1.21.5 linux/amd64",
            "kernel=6.6.0-gentoo",
        ],
        "common_flags": common_flags,
        "cflags": cflags,
        "ldflags": ldflags,
    }


@pytest.fixture()
def sample_results(tmp_path: Path) -> Path:
    """Create a sample benchmark results directory."""
    results = tmp_path / "results"

    for host in ["gentoo-alice", "gentoo-bob"]:
        host_dir = results / host
        host_dir.mkdir(parents=True)

        # Metadata
        flags = "-O2 -march=native -pipe" if host == "gentoo-alice" else "-O3 -march=alderlake -flto"
        (host_dir / "metadata.json").write_text(
            json.dumps(_make_metadata(host, common_flags=flags))
        )

        # Compression benchmarks
        mult = 1.0 if host == "gentoo-alice" else 0.9
        (host_dir / "compression.json").write_text(json.dumps(
            _make_hyperfine_json(
                ("gzip-compress", 1.234 * mult, 0.05),
                ("zstd-compress", 0.456 * mult, 0.02),
                ("lz4-compress", 0.123 * mult, 0.01),
            )
        ))

        # Python benchmarks
        (host_dir / "python.json").write_text(json.dumps(
            _make_hyperfine_json(
                ("fibonacci", 2.5 * mult, 0.1),
                ("json-serde", 1.8 * mult, 0.08),
            )
        ))

        # Gentoo build times (only for alice)
        if host == "gentoo-alice":
            (host_dir / "gentoo_build_times.json").write_text(json.dumps({
                "hostname": host,
                "min_build_threshold_secs": 300,
                "packages": {
                    "www-client/firefox": {
                        "max_duration_secs": 2690,
                        "builds": [
                            {
                                "timestamp": 1772678142,
                                "version": "140.8.0",
                                "duration_secs": 2690,
                                "kernel": "6.18.12-gentoo-dist",
                                "compiler": "x86_64-pc-linux-gnu-clang-21",
                                "cflags": "-march=native -pipe",
                            },
                            {
                                "timestamp": 1772160151,
                                "version": "140.7.1",
                                "duration_secs": 2612,
                                "kernel": "6.12.68",
                                "compiler": "x86_64-pc-linux-gnu-clang-21",
                                "cflags": "-march=native -pipe",
                            },
                        ],
                    },
                },
            }))

        # FFmpeg codec availability
        video_encs = ["libx264", "libx265", "libvpx", "libvpx-vp9", "mpeg2video", "mjpeg"]
        audio_encs = ["aac", "flac", "libmp3lame", "libopus", "libvorbis", "ac3"]
        if host == "gentoo-alice":
            video_encs += ["libsvtav1", "libaom-av1"]
            audio_encs += ["wavpack", "alac"]
        (host_dir / "ffmpeg_codecs.json").write_text(json.dumps({
            "video_encoders": sorted(video_encs),
            "audio_encoders": sorted(audio_encs),
            "video_decoders": ["av1", "h264", "hevc", "mjpeg", "mpeg2video", "vp8", "vp9"],
            "audio_decoders": ["aac", "flac", "mp3", "opus", "vorbis"],
        }))

        # FFmpeg video encoding benchmarks
        ffmpeg_benches = [
            ("h264-encode", 1.2 * mult, 0.05),
            ("h265-encode", 2.8 * mult, 0.1),
            ("vp9-encode", 3.5 * mult, 0.15),
        ]
        if host == "gentoo-alice":
            ffmpeg_benches.append(("av1-svt-encode", 4.2, 0.2))
        (host_dir / "ffmpeg_video_encode.json").write_text(json.dumps(
            _make_hyperfine_json(*ffmpeg_benches)
        ))

    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLoadResults:
    def test_loads_hosts(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        assert set(hosts.keys()) == {"gentoo-alice", "gentoo-bob"}

    def test_loads_benchmarks(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        alice = hosts["gentoo-alice"]
        assert "compression" in alice["benchmarks"]
        assert "python" in alice["benchmarks"]
        assert len(alice["benchmarks"]["compression"]) == 3

    def test_loads_metadata(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        meta = hosts["gentoo-alice"]["metadata"]
        assert meta["cpu_cores"] == 4
        assert "native" in meta["common_flags"]

    def test_missing_dir_exits(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            load_results(tmp_path / "nonexistent")


class TestBuildComparisonTable:
    def test_structure(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        table = build_comparison_table(hosts)
        assert "compression" in table
        assert "gzip-compress" in table["compression"]
        assert "gentoo-alice" in table["compression"]["gzip-compress"]

    def test_values(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        table = build_comparison_table(hosts)
        alice_gzip = table["compression"]["gzip-compress"]["gentoo-alice"]
        assert alice_gzip["mean"] == pytest.approx(1.234, abs=0.001)

    def test_bob_is_faster(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        table = build_comparison_table(hosts)
        alice = table["compression"]["gzip-compress"]["gentoo-alice"]["mean"]
        bob = table["compression"]["gzip-compress"]["gentoo-bob"]["mean"]
        assert bob < alice


class TestExtractFeatures:
    def test_basic_flags(self) -> None:
        meta = _make_metadata("test", common_flags="-O2 -march=native -pipe")
        feat = extract_features(meta)
        assert feat["opt_level"] == "-O2"
        assert feat["march"] == "native"
        assert feat["lto"] == "no"
        assert "pipe" in feat["notable"]

    def test_lto_detection(self) -> None:
        meta = _make_metadata("test", common_flags="-O3 -flto -march=alderlake")
        feat = extract_features(meta)
        assert feat["lto"] == "yes"
        assert feat["opt_level"] == "-O3"

    def test_thin_lto(self) -> None:
        meta = _make_metadata("test", common_flags="-O2 -flto=thin -march=native")
        feat = extract_features(meta)
        assert feat["lto"] == "thin"

    def test_compiler_versions(self) -> None:
        meta = _make_metadata("test")
        feat = extract_features(meta)
        assert "gcc" in feat["ver_gcc"].lower()
        assert "clang" in feat["ver_clang"].lower()

    def test_cpu_clock_ghz(self) -> None:
        meta = _make_metadata("test")
        meta["cpu_mhz"] = 3500
        feat = extract_features(meta)
        assert feat["cpu_clock"] == "3.50 GHz"

    def test_cpu_clock_mhz(self) -> None:
        meta = _make_metadata("test")
        meta["cpu_mhz"] = 800
        feat = extract_features(meta)
        assert feat["cpu_clock"] == "800 MHz"

    def test_cpu_clock_missing(self) -> None:
        meta = _make_metadata("test")
        feat = extract_features(meta)
        assert feat["cpu_clock"] == "—"

    def test_march_native(self) -> None:
        meta = _make_metadata("test")
        meta["march_native"] = "alderlake"
        feat = extract_features(meta)
        assert feat["march_native"] == "alderlake"

    def test_march_native_missing(self) -> None:
        meta = _make_metadata("test")
        feat = extract_features(meta)
        assert feat["march_native"] == "—"

    def test_hardening_flags(self) -> None:
        meta = _make_metadata(
            "test",
            common_flags="-O2 -fstack-protector-strong -D_FORTIFY_SOURCE=2 -fPIE",
            ldflags="-Wl,-z,relro -Wl,-z,now",
        )
        feat = extract_features(meta)
        assert "SSP-strong" in feat["hardening"]
        assert "FORTIFY" in feat["hardening"]
        assert "PIE" in feat["hardening"]
        assert "full-RELRO" in feat["hardening"]

    def test_hardening_partial_relro(self) -> None:
        meta = _make_metadata("test", ldflags="-Wl,-z,relro")
        feat = extract_features(meta)
        assert "partial-RELRO" in feat["hardening"]

    def test_hardening_none(self) -> None:
        meta = _make_metadata("test", common_flags="-O2 -march=native")
        feat = extract_features(meta)
        assert feat["hardening"] == "—"

    def test_kernel_version(self) -> None:
        meta = _make_metadata("test")
        feat = extract_features(meta)
        assert feat["kernel"] == "6.6.0-gentoo"

    def test_kernel_missing(self) -> None:
        meta = _make_metadata("test")
        meta["versions"] = ["gcc=gcc 13.2.0", "clang=clang 17.0.0"]
        feat = extract_features(meta)
        assert feat["kernel"] == "—"


class TestMarkdownReport:
    def test_contains_headers(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        table = build_comparison_table(hosts)
        md = generate_markdown(hosts, table)
        assert "# Gentoo VM Benchmark Report" in md
        assert "## Host Configuration Summary" in md
        assert "## Compression" in md

    def test_contains_hostnames(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        table = build_comparison_table(hosts)
        md = generate_markdown(hosts, table)
        assert "gentoo-alice" in md
        assert "gentoo-bob" in md

    def test_fastest_is_bold(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        table = build_comparison_table(hosts)
        md = generate_markdown(hosts, table)
        # Bob should be faster (0.9x multiplier)
        assert "**" in md


class TestHtmlReport:
    def test_valid_html(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        table = build_comparison_table(hosts)
        html = generate_html(hosts, table)
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html
        assert "Chart.js" in html or "chart.js" in html

    def test_contains_chart_canvas(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        table = build_comparison_table(hosts)
        html = generate_html(hosts, table)
        assert "<canvas" in html
        assert "new Chart(" in html

    def test_contains_data(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        table = build_comparison_table(hosts)
        html = generate_html(hosts, table)
        assert "gentoo-alice" in html
        assert "gzip-compress" in html

    def test_lto_badges(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        table = build_comparison_table(hosts)
        html = generate_html(hosts, table)
        # Alice has no LTO, Bob has LTO
        assert "✗" in html  # Alice no LTO
        assert "✓" in html  # Bob has LTO


class TestEndToEnd:
    def test_write_reports(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        table = build_comparison_table(hosts)

        md = generate_markdown(hosts, table)
        (sample_results / "report.md").write_text(md)
        assert (sample_results / "report.md").exists()
        assert len(md) > 500

        html = generate_html(hosts, table)
        (sample_results / "report.html").write_text(html)
        assert (sample_results / "report.html").exists()
        assert len(html) > 2000


class TestGentooBuildTimes:
    def test_loads_build_times(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        assert "gentoo_build_times" in hosts["gentoo-alice"]
        assert "www-client/firefox" in hosts["gentoo-alice"]["gentoo_build_times"]

    def test_build_times_not_loaded_for_bob(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        assert "gentoo_build_times" not in hosts["gentoo-bob"]

    def test_markdown_contains_build_times(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        table = build_comparison_table(hosts)
        md = generate_markdown(hosts, table)
        assert "Gentoo Package Build Times" in md
        assert "www-client/firefox" in md
        assert "140.8.0" in md
        assert "6.18.12-gentoo-dist" in md
        assert "clang-21" in md
        assert "2026-03-05" in md  # build date from timestamp 1772678142

    def test_html_contains_build_times(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        table = build_comparison_table(hosts)
        html = generate_html(hosts, table)
        assert "Build Times" in html
        assert "www-client/firefox" in html
        assert "140.8.0" in html


class TestFFmpegCodecAvailability:
    def test_loads_codec_data(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        assert "ffmpeg_codecs" in hosts["gentoo-alice"]
        codecs = hosts["gentoo-alice"]["ffmpeg_codecs"]
        assert "libx264" in codecs["video_encoders"]
        assert "libsvtav1" in codecs["video_encoders"]

    def test_bob_has_fewer_codecs(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        alice_ve = hosts["gentoo-alice"]["ffmpeg_codecs"]["video_encoders"]
        bob_ve = hosts["gentoo-bob"]["ffmpeg_codecs"]["video_encoders"]
        assert "libsvtav1" in alice_ve
        assert "libsvtav1" not in bob_ve

    def test_ffmpeg_benchmarks_loaded(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        assert "ffmpeg_video_encode" in hosts["gentoo-alice"]["benchmarks"]
        benches = hosts["gentoo-alice"]["benchmarks"]["ffmpeg_video_encode"]
        names = [b["command"] for b in benches]
        assert "h264-encode" in names
        assert "av1-svt-encode" in names

    def test_markdown_codec_availability(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        table = build_comparison_table(hosts)
        md = generate_markdown(hosts, table)
        assert "FFmpeg Codec Availability" in md
        assert "Video Encoders" in md
        assert "libsvtav1" in md
        assert "✓" in md

    def test_html_codec_availability(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        table = build_comparison_table(hosts)
        html = generate_html(hosts, table)
        assert "Codec Availability" in html
        assert "libsvtav1" in html

    def test_ffmpeg_video_encode_table(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        table = build_comparison_table(hosts)
        assert "ffmpeg_video_encode" in table
        assert "h264-encode" in table["ffmpeg_video_encode"]
        assert "gentoo-alice" in table["ffmpeg_video_encode"]["h264-encode"]

    def test_markdown_ffmpeg_section(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        table = build_comparison_table(hosts)
        md = generate_markdown(hosts, table)
        assert "## FFmpeg Video Encoding" in md
        assert "h264-encode" in md
        assert "vp9-encode" in md


class TestAnonymizeHosts:
    def test_replaces_hostnames(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        anon = anonymize_hosts(hosts)
        assert "gentoo-alice" not in anon
        assert "gentoo-bob" not in anon
        # Sorted: gentoo-alice → Achilles (index 0 in sorted 'g' names??)
        # Actually sorted order: gentoo-alice, gentoo-bob → Zeus, Hera
        # (first two names in the list, assigned by sorted hostname order)
        names = sorted(anon.keys())
        assert len(names) == 2
        assert names[0] == "Hera"
        assert names[1] == "Zeus"

    def test_metadata_hostname_updated(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        anon = anonymize_hosts(hosts)
        for anon_name, data in anon.items():
            assert data["metadata"]["hostname"] == anon_name

    def test_benchmarks_preserved(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        anon = anonymize_hosts(hosts)
        for data in anon.values():
            assert "compression" in data["benchmarks"]
            assert len(data["benchmarks"]["compression"]) == 3

    def test_reports_use_anon_names(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        anon = anonymize_hosts(hosts)
        table = build_comparison_table(anon)
        md = generate_markdown(anon, table)
        assert "gentoo-alice" not in md
        assert "gentoo-bob" not in md
        assert "Zeus" in md
        assert "Hera" in md

    def test_html_uses_anon_names(self, sample_results: Path) -> None:
        hosts = load_results(sample_results)
        anon = anonymize_hosts(hosts)
        table = build_comparison_table(anon)
        html = generate_html(anon, table)
        assert "gentoo-alice" not in html
        assert "gentoo-bob" not in html
        assert "Zeus" in html
