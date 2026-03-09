#!/usr/bin/env python3
"""Generate deterministic benchmark test images for ImageMagick benchmarks.

Creates a 4096×4096 RGB PNG from a fixed random seed, plus JPEG Q90 and
WebP Q90 derivatives.  The same files are transferred to every benchmark host
so that encode/decode timing differences reflect host performance rather than
differences in source image content.

Usage::

    python3 scripts/generate_benchmark_images.py benchmarks/fixtures/

The script is idempotent: existing files are not regenerated unless --force is
passed.

Dependencies: numpy, Pillow (both available on this Gentoo host via system
packages; on other machines use a virtualenv: pip install numpy Pillow).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError as exc:
    sys.exit(
        f"ERROR: {exc}\n"
        "Install required packages:\n"
        "    python3 -m venv /tmp/bench-img-venv\n"
        "    /tmp/bench-img-venv/bin/pip install numpy Pillow\n"
        "Then re-run with /tmp/bench-img-venv/bin/python3\n"
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SEED = 42
DEFAULT_SIZE = 4096


def generate_image(
    output_dir: Path,
    size: int = DEFAULT_SIZE,
    seed: int = DEFAULT_SEED,
    force: bool = False,
) -> None:
    """Generate the PNG, JPEG and WebP fixture files in output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)

    png_path = output_dir / "im_4k.png"
    jpg_path = output_dir / "im_4k_q90.jpg"
    webp_path = output_dir / "im_4k.webp"

    # ── PNG source ───────────────────────────────────────────────────────────
    if png_path.exists() and not force:
        print(f"  Exists, skipping: {png_path}")
    else:
        print(f"Generating {png_path} ({size}x{size}, seed={seed}) ...", flush=True)
        rng = np.random.default_rng(seed)
        # Full-range pseudo-random noise: maximum entropy, worst-case for
        # codecs and most stressful for SIMD pixel pipelines.
        data = rng.integers(0, 256, (size, size, 3), dtype=np.uint8)
        Image.fromarray(data, "RGB").save(png_path, optimize=False, compress_level=1)
        mib = png_path.stat().st_size / (1024 * 1024)
        print(f"  Written: {png_path}  ({mib:.1f} MiB)", flush=True)

    # ── JPEG Q90 derivative ──────────────────────────────────────────────────
    if jpg_path.exists() and not force:
        print(f"  Exists, skipping: {jpg_path}")
    else:
        print(f"Generating {jpg_path} ...", flush=True)
        img = Image.open(png_path)
        img.save(jpg_path, quality=90, subsampling=0)
        kib = jpg_path.stat().st_size / 1024
        print(f"  Written: {jpg_path}  ({kib:.0f} KiB)", flush=True)

    # ── WebP Q90 derivative ──────────────────────────────────────────────────
    if webp_path.exists() and not force:
        print(f"  Exists, skipping: {webp_path}")
    else:
        print(f"Generating {webp_path} ...", flush=True)
        try:
            img = Image.open(png_path)
            img.save(webp_path, quality=90)
            kib = webp_path.stat().st_size / 1024
            print(f"  Written: {webp_path}  ({kib:.0f} KiB)", flush=True)
        except (KeyError, OSError) as exc:
            print(
                f"  Skipped (WebP not available in this Pillow build): {exc}",
                flush=True,
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate deterministic ImageMagick benchmark fixture images.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        help="Directory to write im_4k.png, im_4k_q90.jpg, im_4k.webp",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"Random seed for pixel data (default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=DEFAULT_SIZE,
        help=f"Image width/height in pixels (default: {DEFAULT_SIZE})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate files even if they already exist",
    )
    args = parser.parse_args()

    generate_image(
        output_dir=args.output_dir,
        size=args.size,
        seed=args.seed,
        force=args.force,
    )


if __name__ == "__main__":
    main()
