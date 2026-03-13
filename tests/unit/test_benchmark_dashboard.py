"""Tests for benchmark_dashboard.py — pure-logic functions (no Dash server)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pandas = pytest.importorskip("pandas", reason="pandas required for dashboard tests")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from benchmark_dashboard import build_df  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _host(
    benchmarks: dict | None = None,
    os_family: str = "Gentoo",
    hostname: str = "h1",
) -> dict:
    return {
        "metadata": {"hostname": hostname, "os_family": os_family},
        "benchmarks": benchmarks or {},
    }


def _bench(command: str = "cmd", mean: float = 1.0, stddev: float = 0.1) -> dict:
    return {
        "command": command,
        "mean": mean,
        "stddev": stddev,
        "min": mean - stddev,
        "max": mean + stddev,
        "median": mean,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildDf:
    """Tests for the build_df() function."""

    def test_empty_hosts_returns_empty_dataframe(self) -> None:
        df, host_os = build_df({})
        assert df.empty
        assert host_os == {}

    def test_empty_hosts_has_required_columns(self) -> None:
        df, _host_os = build_df({})
        required = {
            "category", "benchmark", "host", "os_family",
            "mean", "stddev", "min", "max", "median",
        }
        assert required.issubset(set(df.columns))

    def test_single_host_single_benchmark_creates_one_row(self) -> None:
        hosts = {
            "h1": _host({"compression": [_bench("gzip", 1.2, 0.05)]})
        }
        df, _host_os = build_df(hosts)
        assert len(df) == 1
        assert df.iloc[0]["benchmark"] == "gzip"
        assert df.iloc[0]["mean"] == pytest.approx(1.2)

    def test_multiple_benchmarks_create_multiple_rows(self) -> None:
        hosts = {
            "h1": _host({
                "compression": [
                    _bench("gzip", 1.2, 0.05),
                    _bench("zstd", 0.4, 0.02),
                ]
            })
        }
        df, _host_os = build_df(hosts)
        assert len(df) == 2

    def test_multiple_hosts_rows_include_all_hosts(self) -> None:
        hosts = {
            "h1": _host({"compression": [_bench("gzip", 1.0, 0.05)]}, hostname="h1"),
            "h2": _host({"compression": [_bench("gzip", 0.9, 0.04)]}, hostname="h2"),
        }
        df, _host_os = build_df(hosts)
        assert len(df) == 2
        assert set(df["host"].unique()) == {"h1", "h2"}

    def test_multiple_categories_all_included(self) -> None:
        hosts = {
            "h1": _host({
                "compression": [_bench("gzip", 1.0, 0.05)],
                "python": [_bench("fibonacci", 2.5, 0.1)],
            })
        }
        df, _host_os = build_df(hosts)
        assert len(df) == 2
        assert set(df["category"].unique()) == {"compression", "python"}

    def test_host_os_mapping_extracted_correctly(self) -> None:
        hosts = {
            "h1": _host(os_family="Gentoo", hostname="h1"),
            "h2": _host(os_family="Ubuntu", hostname="h2"),
        }
        _ignored, host_os = build_df(hosts)
        assert host_os == {"h1": "Gentoo", "h2": "Ubuntu"}

    def test_missing_metadata_falls_back_to_unknown(self) -> None:
        hosts = {
            "h1": {
                "metadata": {},  # no os_family key
                "benchmarks": {"compression": [_bench("gzip")]},
            }
        }
        _ignored, host_os = build_df(hosts)
        assert host_os["h1"] == "Unknown"

    def test_missing_benchmarks_key_produces_empty_df(self) -> None:
        hosts = {
            "h1": {"metadata": {"hostname": "h1", "os_family": "Gentoo"}}
        }
        df, host_os = build_df(hosts)
        assert df.empty
        assert host_os["h1"] == "Gentoo"

    def test_boot_times_key_not_in_df(self) -> None:
        """boot_times is stored separately in hosts; should not appear in DF."""
        hosts = {
            "h1": {
                "metadata": {"hostname": "h1", "os_family": "Gentoo"},
                "benchmarks": {"compression": [_bench("gzip")]},
                "boot_times": {"available": True, "total_sec": 25.0},
            }
        }
        df, _host_os = build_df(hosts)
        assert "boot_times" not in df["category"].values

    def test_numeric_columns_are_float(self) -> None:
        hosts = {
            "h1": _host({"compression": [_bench("gzip", 1.23, 0.01)]})
        }
        df, _host_os = build_df(hosts)
        for col in ("mean", "stddev", "min", "max", "median"):
            assert df[col].dtype == float, f"{col} should be float"

    def test_cross_product_rows_correct(self) -> None:
        """3 hosts × 2 categories × 2 benchmarks each = 12 rows."""
        hosts = {
            f"h{i}": _host({
                "compression": [_bench("gzip"), _bench("zstd")],
                "python": [_bench("fib"), _bench("json")],
            }, hostname=f"h{i}")
            for i in range(3)
        }
        df, _host_os = build_df(hosts)
        assert len(df) == 12
