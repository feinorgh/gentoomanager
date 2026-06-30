"""Unit tests for CFLAGS analysis parser."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas", reason="pandas required for cflags analysis tests")

# Import the parser module from scripts directory
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import benchmarks_cflags_analysis as cflags_parser


class TestClassifyMarchClass:
    """Tests for classify_march_class function."""

    def test_classify_march_native_like(self) -> None:
        """Detect -march=native as native_like."""
        assert cflags_parser.classify_march_class("-O2 -pipe -march=native") == "native_like"

    def test_classify_march_native_mtune(self) -> None:
        """Detect -mtune=native as native_like."""
        assert cflags_parser.classify_march_class("-O2 -mtune=native") == "native_like"

    def test_classify_march_generic_like(self) -> None:
        """Detect x86-64 variants as generic_like."""
        assert cflags_parser.classify_march_class("-O2 -pipe -march=x86-64-v3") == "generic_like"

    def test_classify_march_generic_like_base(self) -> None:
        """Detect base x86-64 as generic_like."""
        assert cflags_parser.classify_march_class("-O2 -march=x86-64") == "generic_like"

    def test_classify_march_unknown(self) -> None:
        """Unknown -march values return unknown."""
        assert cflags_parser.classify_march_class("-O2 -pipe") == "unknown"


class TestParseOptLevel:
    """Tests for parse_opt_level function."""

    def test_parse_opt_level_o2(self) -> None:
        """Parse -O2 optimization level."""
        assert cflags_parser.parse_opt_level("-O2") == "O2"

    def test_parse_opt_level_o3(self) -> None:
        """Parse -O3 optimization level."""
        assert cflags_parser.parse_opt_level("-O3") == "O3"

    def test_parse_opt_level_os(self) -> None:
        """Parse -Os optimization level."""
        assert cflags_parser.parse_opt_level("-Os") == "Os"

    def test_parse_opt_level_conflict(self) -> None:
        """Multiple -O flags return 'other'."""
        assert cflags_parser.parse_opt_level("-O2 -O3") == "other"

    def test_parse_opt_level_missing(self) -> None:
        """No -O flag returns 'unknown'."""
        assert cflags_parser.parse_opt_level("-pipe") == "unknown"

    def test_parse_opt_level_ofast(self) -> None:
        """Parse -Ofast optimization level."""
        assert cflags_parser.parse_opt_level("-Ofast -pipe") == "Ofast"

    def test_parse_opt_level_ofast_conflict(self) -> None:
        """Multiple -O flags with -Ofast return 'other'."""
        assert cflags_parser.parse_opt_level("-O2 -Ofast") == "other"

    def test_parse_opt_level_wl_at_start(self) -> None:
        """Handle -Wl linker flags at string start."""
        assert cflags_parser.parse_opt_level("-Wl,-O2") == "O2"

    def test_parse_opt_level_wl_conflict(self) -> None:
        """Detect conflict when -Wl contains -O flag and compiler has different one."""
        assert cflags_parser.parse_opt_level("-Wl,-O3 -O2") == "other"


class TestParseLtoMode:
    """Tests for parse_lto_mode function."""

    def test_parse_lto_on(self) -> None:
        """Parse -flto as 'on'."""
        assert cflags_parser.parse_lto_mode("-O2 -flto") == "on"

    def test_parse_lto_auto(self) -> None:
        """Parse -flto=auto as 'auto'."""
        assert cflags_parser.parse_lto_mode("-O2 -flto=auto") == "auto"

    def test_parse_lto_thin(self) -> None:
        """Parse -flto=thin as 'thin'."""
        assert cflags_parser.parse_lto_mode("-O2 -flto=thin") == "thin"

    def test_parse_lto_off(self) -> None:
        """No -flto flag returns 'off'."""
        assert cflags_parser.parse_lto_mode("-O2 -pipe") == "off"


class TestParsePgoMode:
    """Tests for parse_pgo_mode function."""

    def test_parse_pgo_generate(self) -> None:
        """Parse -fprofile-generate as 'generate'."""
        assert cflags_parser.parse_pgo_mode("-O2 -fprofile-generate") == "generate"

    def test_parse_pgo_use(self) -> None:
        """Parse -fprofile-use as 'use'."""
        assert cflags_parser.parse_pgo_mode("-O2 -fprofile-use") == "use"

    def test_parse_pgo_both(self) -> None:
        """Both generate and use returns 'both_or_other'."""
        assert (
            cflags_parser.parse_pgo_mode("-O2 -fprofile-generate -fprofile-use") == "both_or_other"
        )

    def test_parse_pgo_off(self) -> None:
        """No PGO flags returns 'off'."""
        assert cflags_parser.parse_pgo_mode("-O2 -pipe") == "off"


class TestParseGraphiteMode:
    """Tests for parse_graphite_mode function."""

    def test_parse_graphite_on(self) -> None:
        """Parse -fgraphite-identity as 'on'."""
        assert cflags_parser.parse_graphite_mode("-O2 -fgraphite-identity") == "on"

    def test_parse_graphite_off(self) -> None:
        """No graphite flags returns 'off'."""
        assert cflags_parser.parse_graphite_mode("-O2 -pipe") == "off"


class TestNormalizeFlagText:
    """Tests for normalize_flag_text function."""

    def test_normalize_flag_text_all_present(self) -> None:
        """Normalize with all flag types present."""
        result = cflags_parser.normalize_flag_text("-O2 -pipe", "-march=native", "-lpthread")
        assert result == "-o2 -pipe -march=native -lpthread"

    def test_normalize_flag_text_with_none(self) -> None:
        """Normalize with None values."""
        result = cflags_parser.normalize_flag_text("-O2", None, None)
        assert result == "-o2"

    def test_normalize_flag_text_empty_strings(self) -> None:
        """Normalize with empty strings."""
        result = cflags_parser.normalize_flag_text("", "-O2", "")
        assert result == "-o2"


@pytest.fixture
def sample_df() -> pd.DataFrame:
    """Create a sample dataframe for enrichment tests."""
    return pd.DataFrame(
        {
            "os": ["Gentoo", "Gentoo", "Ubuntu", "Fedora"],
            "common_flags": [
                "-O2 -pipe",
                "-O2 -pipe",
                "-O2",
                "-O2",
            ],
            "cflags": [
                "-march=native -flto -fprofile-generate",
                "-march=x86-64-v3",
                "-march=x86-64",
                "-march=native",
            ],
            "ldflags": ["-Wl,-as-needed", "-Wl,-as-needed", "", ""],
            "benchmark_name": ["test1", "test2", "test3", "test4"],
        }
    )


class TestEnrichGentooFlagsDimensions:
    """Tests for enrich_gentoo_cflags_dimensions function."""

    def test_enrich_adds_expected_columns(self, sample_df: pd.DataFrame) -> None:
        """Enrichment adds all expected columns."""
        enriched = cflags_parser.enrich_gentoo_cflags_dimensions(sample_df)
        expected_cols = {
            "march_class",
            "opt_level",
            "lto_mode",
            "pgo_mode",
            "graphite_mode",
        }
        assert expected_cols <= set(enriched.columns)

    def test_enrich_preserves_original_columns(self, sample_df: pd.DataFrame) -> None:
        """Enrichment preserves original columns."""
        enriched = cflags_parser.enrich_gentoo_cflags_dimensions(sample_df)
        original_cols = set(sample_df.columns)
        assert original_cols <= set(enriched.columns)

    def test_enrich_only_affects_gentoo_rows(self, sample_df: pd.DataFrame) -> None:
        """Only Gentoo rows get dimensions; others get 'unknown'."""
        enriched = cflags_parser.enrich_gentoo_cflags_dimensions(sample_df)
        non_gentoo = enriched[enriched["os"] != "Gentoo"]
        assert non_gentoo["march_class"].eq("unknown").all()
        assert non_gentoo["opt_level"].eq("unknown").all()
        assert non_gentoo["lto_mode"].eq("unknown").all()
        assert non_gentoo["pgo_mode"].eq("unknown").all()
        assert non_gentoo["graphite_mode"].eq("unknown").all()

    def test_enrich_gentoo_rows_parsed_correctly(self, sample_df: pd.DataFrame) -> None:
        """Gentoo rows are parsed correctly."""
        enriched = cflags_parser.enrich_gentoo_cflags_dimensions(sample_df)
        gentoo_rows = enriched[enriched["os"] == "Gentoo"]

        # First row: native+flto+pgo
        assert gentoo_rows.iloc[0]["march_class"] == "native_like"
        assert gentoo_rows.iloc[0]["opt_level"] == "O2"
        assert gentoo_rows.iloc[0]["lto_mode"] == "on"
        assert gentoo_rows.iloc[0]["pgo_mode"] == "generate"

        # Second row: x86-64-v3
        assert gentoo_rows.iloc[1]["march_class"] == "generic_like"
        assert gentoo_rows.iloc[1]["opt_level"] == "O2"
        assert gentoo_rows.iloc[1]["lto_mode"] == "off"
        assert gentoo_rows.iloc[1]["pgo_mode"] == "off"
