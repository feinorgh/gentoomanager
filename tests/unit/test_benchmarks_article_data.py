"""Unit tests for scripts/benchmarks_article_data.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import benchmarks_article_data as bad  # noqa: E402


def test_detects_gentoo_tuning_flags() -> None:
    metadata = {
        "common_flags": "-O2 -pipe -fgraphite-identity -floop-interchange -flto=auto",
        "cflags": "-O2 -pipe -fprofile-use",
        "ldflags": "-Wl,-O1",
    }

    tuning = bad.extract_gentoo_tuning(metadata)

    assert tuning["graphite_enabled"] is True
    assert tuning["lto_enabled"] is True
    assert tuning["pgo_enabled"] is True


def test_load_benchmark_rows_reads_metadata_and_hyperfine_json(tmp_path: Path) -> None:
    host_dir = tmp_path / "gentoo-example"
    host_dir.mkdir()
    (host_dir / "metadata.json").write_text(
        json.dumps(
            {
                "hostname": "gentoo-example",
                "os": "Gentoo",
                "os_family": "Gentoo",
                "gentoo_profile": "default/linux/amd64/23.0/systemd",
                "common_flags": "-O2 -pipe -flto=auto",
                "cflags": "-O2 -pipe",
                "ldflags": "-Wl,-O1",
                "cpu_model": "Intel(R) Core(TM) i7-9700 CPU @ 3.00GHz",
                "versions": [
                    "ffmpeg=ffmpeg version 8.1",
                    "gcc=gcc (Gentoo) 15.2.1",
                ],
            }
        )
    )
    (host_dir / "compression.json").write_text(
        json.dumps(
            {
                "results": [
                    {"command": "gzip -9", "mean": 1.25, "stddev": 0.07},
                    {"command": "zstd -19", "mean": 0.95, "stddev": 0.03},
                ]
            }
        )
    )

    rows = bad.load_benchmark_rows(tmp_path, anonymize_hosts=False)

    assert len(rows) == 2
    assert {row["benchmark"] for row in rows} == {"gzip -9", "zstd -19"}
    assert all(row["host"] == "gentoo-example" for row in rows)
    assert all(row["category"] == "compression" for row in rows)
    assert all(row["os_version"] == "" for row in rows)
    assert all(row["os_label"] == "Gentoo" for row in rows)
    assert all(row["lto_enabled"] is True for row in rows)
    assert all(row["cpu_model"] == "Intel(R) Core(TM) i7-9700 CPU @ 3.00GHz" for row in rows)
    assert all(row["tool_versions"]["ffmpeg"].startswith("ffmpeg version") for row in rows)


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
                "distro_label": "CachyOS Linux rolling",
                "versions": [],
            }
        )
    )
    (host_dir / "compression.json").write_text(
        json.dumps({"results": [{"command": "gzip -9", "mean": 1.0, "stddev": 0.1}]})
    )

    rows = bad.load_benchmark_rows(tmp_path, anonymize_hosts=False)

    assert len(rows) == 1
    assert rows[0]["distro_label"] == "CachyOS Linux rolling"


def test_load_benchmark_rows_skips_invalid_json_files(tmp_path: Path) -> None:
    host_dir = tmp_path / "gentoo-example"
    host_dir.mkdir()
    (host_dir / "metadata.json").write_text(
        json.dumps(
            {
                "hostname": "gentoo-example",
                "os": "Gentoo",
                "os_family": "Gentoo",
                "versions": [],
            }
        )
    )
    (host_dir / "compression.json").write_text("not-json")
    (host_dir / "crypto_hash.json").write_text(
        json.dumps({"results": [{"command": "sha256sum", "mean": 0.77, "stddev": 0.02}]})
    )

    rows = bad.load_benchmark_rows(tmp_path, anonymize_hosts=False)

    assert len(rows) == 1
    assert rows[0]["category"] == "crypto_hash"


def test_load_benchmark_rows_anonymizes_hosts_by_default(tmp_path: Path) -> None:
    host_a = tmp_path / "host-zeta"
    host_b = tmp_path / "host-alpha"
    host_a.mkdir()
    host_b.mkdir()
    (host_a / "metadata.json").write_text(json.dumps({"hostname": "host-zeta", "versions": []}))
    (host_b / "metadata.json").write_text(json.dumps({"hostname": "host-alpha", "versions": []}))
    (host_a / "compression.json").write_text(
        json.dumps({"results": [{"command": "gzip -9", "mean": 1.0, "stddev": 0.1}]})
    )
    (host_b / "compression.json").write_text(
        json.dumps({"results": [{"command": "gzip -9", "mean": 1.2, "stddev": 0.1}]})
    )

    rows = bad.load_benchmark_rows(tmp_path)
    hosts = sorted({row["host"] for row in rows})
    host_slugs = sorted({row["host_slug"] for row in rows})

    assert hosts == ["Hera", "Zeus"]
    assert host_slugs == ["host-alpha", "host-zeta"]
    assert "host-alpha" not in hosts
    assert "host-zeta" not in hosts


def test_load_benchmark_rows_preserves_hosts_when_anonymization_disabled(tmp_path: Path) -> None:
    host_dir = tmp_path / "gentoo-example"
    host_dir.mkdir()
    (host_dir / "metadata.json").write_text(
        json.dumps(
            {"hostname": "gentoo-example", "os": "Gentoo", "os_family": "Gentoo", "versions": []}
        )
    )
    (host_dir / "compression.json").write_text(
        json.dumps({"results": [{"command": "gzip -9", "mean": 1.25, "stddev": 0.07}]})
    )

    rows = bad.load_benchmark_rows(tmp_path, anonymize_hosts=False)

    assert len(rows) == 1
    assert rows[0]["host"] == "gentoo-example"
    assert rows[0]["host_slug"] == "gentoo-example"


def test_load_benchmark_rows_uses_raw_os_label_when_distro_label_missing(tmp_path: Path) -> None:
    host_dir = tmp_path / "cachyos-jessica"
    host_dir.mkdir()
    (host_dir / "metadata.json").write_text(
        json.dumps(
            {
                "hostname": "cachyos-jessica",
                "os": "Archlinux",
                "os_version": "rolling",
                "os_family": "Archlinux",
                "versions": [],
            }
        )
    )
    (host_dir / "compression.json").write_text(
        json.dumps({"results": [{"command": "gzip -9", "mean": 1.0, "stddev": 0.1}]})
    )

    rows = bad.load_benchmark_rows(tmp_path, anonymize_hosts=False)

    assert len(rows) == 1
    assert rows[0]["os_label"] == "Archlinux rolling"
    assert rows[0]["distro_label"] == "Archlinux rolling"


def test_benchmarks_article_data_has_no_shebang() -> None:
    script_path = REPO_ROOT / "scripts" / "benchmarks_article_data.py"
    first_line = script_path.read_text(encoding="utf-8").splitlines()[0]
    assert not first_line.startswith("#!"), (
        "scripts/benchmarks_article_data.py must not have a shebang "
        "to satisfy ansible-test sanity for non-module files"
    )


def test_article_includes_cflags_deep_dive_heading() -> None:
    qmd = Path(REPO_ROOT / "docs/benchmarks-article/index.qmd").read_text(encoding="utf-8")
    assert "## Gentoo CFLAGS Deep-Dive" in qmd


def test_article_dataset_summary_formats_host_as_markdown_link() -> None:
    qmd = Path(REPO_ROOT / "docs/benchmarks-article/index.qmd").read_text(encoding="utf-8")

    if "## Dataset Summary" not in qmd:
        raise AssertionError("Article must include a Dataset Summary section")
    if 'summary["host"]' not in qmd:
        raise AssertionError("Dataset Summary logic must reference the host column")
    if 'summary["host_slug"]' not in qmd:
        raise AssertionError("Dataset Summary logic must reference the canonical host_slug column")
    if "hosts/{host_slug}.html" not in qmd:
        raise AssertionError("Dataset Summary host-link logic must target hosts/{host_slug}.html")
