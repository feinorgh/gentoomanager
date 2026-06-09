"""Unit tests for scripts/benchmarks_article_catalog.py."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import benchmarks_article_catalog as bac  # noqa: E402


class TestCategoryMeta:
    def test_time_metric_lower_is_better(self) -> None:
        meta = bac.CategoryMeta(
            title="Test",
            description="desc",
            metric_kind="time",
            unit_label="seconds",
            y_axis_label="Runtime (seconds)",
            analysis_hint="hint",
        )
        assert meta.lower_is_better is True

    def test_rate_metric_lower_is_not_better(self) -> None:
        meta = bac.CategoryMeta(
            title="Test",
            description="desc",
            metric_kind="rate",
            unit_label="MB/s",
            y_axis_label="Throughput (MB/s)",
            analysis_hint="hint",
        )
        assert meta.lower_is_better is False

    def test_time_metric_direction_note(self) -> None:
        meta = bac.CategoryMeta(
            title="T",
            description="d",
            metric_kind="time",
            unit_label="s",
            y_axis_label="Runtime (seconds)",
            analysis_hint="h",
        )
        assert meta.direction_note == "lower is better"

    def test_rate_metric_direction_note(self) -> None:
        meta = bac.CategoryMeta(
            title="T",
            description="d",
            metric_kind="rate",
            unit_label="MB/s",
            y_axis_label="Throughput (MB/s)",
            analysis_hint="h",
        )
        assert meta.direction_note == "higher is better"

    def test_time_metric_winner_label(self) -> None:
        meta = bac.CategoryMeta(
            title="T",
            description="d",
            metric_kind="time",
            unit_label="s",
            y_axis_label="Y",
            analysis_hint="h",
        )
        assert meta.winner_label == "fastest"

    def test_rate_metric_winner_label(self) -> None:
        meta = bac.CategoryMeta(
            title="T",
            description="d",
            metric_kind="rate",
            unit_label="MB/s",
            y_axis_label="Y",
            analysis_hint="h",
        )
        assert meta.winner_label == "highest throughput"

    def test_time_metric_sort_ascending(self) -> None:
        meta = bac.CategoryMeta(
            title="T",
            description="d",
            metric_kind="time",
            unit_label="s",
            y_axis_label="Y",
            analysis_hint="h",
        )
        assert meta.sort_ascending is True

    def test_rate_metric_sort_descending(self) -> None:
        meta = bac.CategoryMeta(
            title="T",
            description="d",
            metric_kind="rate",
            unit_label="MB/s",
            y_axis_label="Y",
            analysis_hint="h",
        )
        assert meta.sort_ascending is False

    def test_frozen_prevents_mutation(self) -> None:
        import dataclasses

        meta = bac.CategoryMeta(
            title="T",
            description="d",
            metric_kind="time",
            unit_label="s",
            y_axis_label="Y",
            analysis_hint="h",
        )
        try:
            meta.title = "mutated"  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except dataclasses.FrozenInstanceError:
            pass


class TestGetCategoryMeta:
    def test_known_category_returns_catalog_entry(self) -> None:
        meta = bac.get_category_meta("compression")
        assert meta.title == "Compression"
        assert "gzip" in meta.description.lower() or "compress" in meta.description.lower()
        assert meta.metric_kind == "time"

    def test_known_category_crypto(self) -> None:
        meta = bac.get_category_meta("crypto")
        assert "crypto" in meta.title.lower() or "cryptograph" in meta.title.lower()
        assert meta.lower_is_better is True

    def test_known_category_linker(self) -> None:
        meta = bac.get_category_meta("linker")
        assert "link" in meta.title.lower()
        assert "lld" in meta.analysis_hint.lower() or "linker" in meta.analysis_hint.lower()

    def test_known_category_gentoo_build_times(self) -> None:
        meta = bac.get_category_meta("gentoo_build_times")
        assert "build" in meta.title.lower()
        assert meta.metric_kind == "time"

    def test_unknown_category_returns_default_meta(self) -> None:
        meta = bac.get_category_meta("nonexistent_category_xyz")
        assert meta.title == "Nonexistent Category Xyz"
        assert meta.metric_kind == "time"
        assert meta.lower_is_better is True

    def test_unknown_category_title_uses_title_case(self) -> None:
        meta = bac.get_category_meta("my_custom_bench")
        assert meta.title == "My Custom Bench"

    def test_unknown_category_has_fallback_description(self) -> None:
        meta = bac.get_category_meta("unknown_thing")
        assert len(meta.description) > 20
        assert "time" in meta.description.lower() or "lower" in meta.description.lower()

    def test_unknown_category_has_fallback_analysis_hint(self) -> None:
        meta = bac.get_category_meta("unknown_thing")
        assert len(meta.analysis_hint) > 5

    def test_all_catalog_entries_have_non_empty_fields(self) -> None:
        for category in bac.catalog_categories():
            meta = bac.get_category_meta(category)
            assert meta.title, f"{category}: title is empty"
            assert meta.description, f"{category}: description is empty"
            assert meta.unit_label, f"{category}: unit_label is empty"
            assert meta.y_axis_label, f"{category}: y_axis_label is empty"
            assert meta.analysis_hint, f"{category}: analysis_hint is empty"

    def test_all_catalog_entries_are_time_based(self) -> None:
        # All current categories store hyperfine mean_s timing, so all should be time-based.
        for category in bac.catalog_categories():
            meta = bac.get_category_meta(category)
            assert meta.metric_kind == "time", (
                f"{category}: expected metric_kind='time', got '{meta.metric_kind}'"
            )

    def test_catalog_covers_known_benchmark_categories(self) -> None:
        expected = {
            "bash",
            "boot_time",
            "compression",
            "compiler",
            "coreutils",
            "crypto",
            "disk",
            "ffmpeg",
            "gentoo_build_times",
            "gimp",
            "imagemagick",
            "inkscape",
            "linker",
            "memory",
            "numeric",
            "octave",
            "opencv",
            "process",
            "python",
            "sqlite",
            "startup",
        }
        catalog = set(bac.catalog_categories())
        missing = expected - catalog
        assert not missing, f"Catalog is missing expected categories: {missing}"


class TestCatalogCategories:
    def test_returns_list_of_strings(self) -> None:
        cats = bac.catalog_categories()
        assert isinstance(cats, list)
        assert all(isinstance(c, str) for c in cats)

    def test_non_empty(self) -> None:
        assert len(bac.catalog_categories()) > 0

    def test_no_duplicates(self) -> None:
        cats = bac.catalog_categories()
        assert len(cats) == len(set(cats))

    def test_includes_core_categories(self) -> None:
        cats = bac.catalog_categories()
        for expected in ("compression", "crypto", "memory", "disk", "process"):
            assert expected in cats, f"Expected '{expected}' in catalog_categories()"


def test_benchmarks_article_catalog_has_no_shebang() -> None:
    script_path = REPO_ROOT / "scripts" / "benchmarks_article_catalog.py"
    first_line = script_path.read_text(encoding="utf-8").splitlines()[0]
    assert not first_line.startswith("#!"), (
        "scripts/benchmarks_article_catalog.py must not have a shebang "
        "to satisfy ansible-test sanity for non-module files"
    )
