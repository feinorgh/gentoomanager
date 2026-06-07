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

    rows = bad.load_benchmark_rows(tmp_path)

    assert len(rows) == 2
    assert {row["benchmark"] for row in rows} == {"gzip -9", "zstd -19"}
    assert all(row["host"] == "gentoo-example" for row in rows)
    assert all(row["category"] == "compression" for row in rows)
    assert all(row["lto_enabled"] is True for row in rows)
    assert all(row["tool_versions"]["ffmpeg"].startswith("ffmpeg version") for row in rows)


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

    rows = bad.load_benchmark_rows(tmp_path)

    assert len(rows) == 1
    assert rows[0]["category"] == "crypto_hash"
