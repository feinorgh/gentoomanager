"""Unit tests for scripts/generate_benchmark_images.py."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

# ---------------------------------------------------------------------------
# Import guard — skip all tests if numpy or Pillow are unavailable.
# ---------------------------------------------------------------------------

numpy = pytest.importorskip("numpy", reason="numpy not installed")
PIL = pytest.importorskip("PIL", reason="Pillow not installed")

import generate_benchmark_images as gbi  # noqa: E402

# ---------------------------------------------------------------------------
# generate_image
# ---------------------------------------------------------------------------


class TestGenerateImage:
    def test_creates_png_file(self, tmp_path: Path) -> None:
        gbi.generate_image(tmp_path, size=64, seed=42)
        assert (tmp_path / "im_4k.png").exists()

    def test_creates_jpeg_file(self, tmp_path: Path) -> None:
        gbi.generate_image(tmp_path, size=64, seed=42)
        assert (tmp_path / "im_4k_q90.jpg").exists()

    def test_png_has_correct_dimensions(self, tmp_path: Path) -> None:
        gbi.generate_image(tmp_path, size=64, seed=42)
        from PIL import Image

        img = Image.open(tmp_path / "im_4k.png")
        assert img.size == (64, 64)

    def test_png_is_rgb(self, tmp_path: Path) -> None:
        gbi.generate_image(tmp_path, size=64, seed=42)
        from PIL import Image

        img = Image.open(tmp_path / "im_4k.png")
        assert img.mode == "RGB"

    def test_deterministic_with_same_seed(self, tmp_path: Path) -> None:
        out_a = tmp_path / "a"
        out_b = tmp_path / "b"
        gbi.generate_image(out_a, size=32, seed=7)
        gbi.generate_image(out_b, size=32, seed=7)
        assert (out_a / "im_4k.png").read_bytes() == (out_b / "im_4k.png").read_bytes()

    def test_different_seeds_produce_different_images(self, tmp_path: Path) -> None:
        out_a = tmp_path / "a"
        out_b = tmp_path / "b"
        gbi.generate_image(out_a, size=32, seed=1)
        gbi.generate_image(out_b, size=32, seed=2)
        assert (out_a / "im_4k.png").read_bytes() != (out_b / "im_4k.png").read_bytes()

    def test_skips_existing_files_without_force(self, tmp_path: Path) -> None:
        gbi.generate_image(tmp_path, size=32, seed=1)
        mtime_before = (tmp_path / "im_4k.png").stat().st_mtime
        gbi.generate_image(tmp_path, size=32, seed=1)
        mtime_after = (tmp_path / "im_4k.png").stat().st_mtime
        assert mtime_before == mtime_after

    def test_force_regenerates_existing_files(self, tmp_path: Path) -> None:
        gbi.generate_image(tmp_path, size=32, seed=1)
        mtime_before = (tmp_path / "im_4k.png").stat().st_mtime_ns
        import time

        time.sleep(0.05)
        gbi.generate_image(tmp_path, size=32, seed=1, force=True)
        mtime_after = (tmp_path / "im_4k.png").stat().st_mtime_ns
        assert mtime_after > mtime_before

    def test_creates_output_directory(self, tmp_path: Path) -> None:
        out = tmp_path / "new" / "nested"
        gbi.generate_image(out, size=32, seed=1)
        assert out.is_dir()

    def test_custom_size_respected(self, tmp_path: Path) -> None:
        gbi.generate_image(tmp_path, size=128, seed=42)
        from PIL import Image

        img = Image.open(tmp_path / "im_4k.png")
        assert img.size == (128, 128)

    def test_webp_created_when_pillow_supports_it(self, tmp_path: Path) -> None:
        gbi.generate_image(tmp_path, size=32, seed=42)
        webp = tmp_path / "im_4k.webp"
        # WebP support depends on the Pillow build; if created it must be a file
        if webp.exists():
            assert webp.stat().st_size > 0

    def test_jpeg_quality_is_nonzero(self, tmp_path: Path) -> None:
        gbi.generate_image(tmp_path, size=32, seed=42)
        assert (tmp_path / "im_4k_q90.jpg").stat().st_size > 0


# ---------------------------------------------------------------------------
# main() — CLI argument parsing
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_calls_generate_image(self, tmp_path: Path) -> None:
        with patch.object(gbi, "generate_image") as mock_gen:
            with patch("sys.argv", ["prog", str(tmp_path)]):
                gbi.main()
        mock_gen.assert_called_once()
        call_kwargs = mock_gen.call_args
        assert call_kwargs[1]["seed"] == gbi.DEFAULT_SEED or call_kwargs[0][2] == gbi.DEFAULT_SEED

    def test_main_passes_force_flag(self, tmp_path: Path) -> None:
        with patch.object(gbi, "generate_image") as mock_gen:
            with patch("sys.argv", ["prog", str(tmp_path), "--force"]):
                gbi.main()
        call = mock_gen.call_args
        assert call[1].get("force", False) or (len(call[0]) >= 4 and call[0][3])

    def test_main_passes_custom_seed(self, tmp_path: Path) -> None:
        with patch.object(gbi, "generate_image") as mock_gen:
            with patch("sys.argv", ["prog", str(tmp_path), "--seed", "99"]):
                gbi.main()
        call = mock_gen.call_args
        seed = call[1].get("seed") or call[0][2]
        assert seed == 99

    def test_main_passes_custom_size(self, tmp_path: Path) -> None:
        with patch.object(gbi, "generate_image") as mock_gen:
            with patch("sys.argv", ["prog", str(tmp_path), "--size", "256"]):
                gbi.main()
        call = mock_gen.call_args
        size = call[1].get("size") or call[0][1]
        assert size == 256
