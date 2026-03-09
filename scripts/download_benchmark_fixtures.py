#!/usr/bin/env python3
"""Download standardised benchmark fixture files.

Downloads and prepares:

  - **Silesia corpus** (211 MiB, 12 files) — compression benchmarks
    http://sun.aei.polsl.pl/~sdeor/corpus/silesia.zip
  - **Canterbury corpus** (2.8 MiB, 18 files) — compression benchmarks
    https://corpus.canterbury.ac.nz/resources/cantrbry.tar.gz
  - **Big Buck Bunny 720p clip** (≈30 s, FFV1 lossless + PCM audio) — FFmpeg benchmarks
    https://download.blender.org/demo/movies/BBB/bbb_sunflower_720p_30fps_normal.mp4
    © Blender Foundation, CC BY 3.0 — https://peach.blender.org/
  - **Kodak Lossless True Color Image Suite** (24 PNG, ≈18 MiB) — ImageMagick benchmarks
    http://r0k.us/graphics/kodak/kodak/kodimNN.png

All files are written to the specified output directory.  Re-running is
safe — existing files are skipped unless ``--force`` is passed.

Usage::

    python3 scripts/download_benchmark_fixtures.py benchmarks/fixtures/
    python3 scripts/download_benchmark_fixtures.py benchmarks/fixtures/ --skip-video
    python3 scripts/download_benchmark_fixtures.py benchmarks/fixtures/ --force

Requires FFmpeg to be installed on the controller for the Big Buck Bunny
processing step (``--skip-video`` bypasses this requirement).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Download helper
# ---------------------------------------------------------------------------

def _progress(count: int, block: int, total: int) -> None:
    if total <= 0:
        return
    pct = min(count * block * 100 // total, 100)
    done = pct // 2
    bar = "=" * done + ">" + " " * (50 - done)
    mb = count * block / (1024 * 1024)
    tmb = total / (1024 * 1024)
    print(f"\r  [{bar}] {pct}%  {mb:.1f}/{tmb:.1f} MiB", end="", flush=True)


def download(url: str, dest: Path, desc: str, force: bool = False) -> bool:
    """Download *url* to *dest*.  Return True on success."""
    if dest.exists() and not force:
        mib = dest.stat().st_size / (1024 * 1024)
        print(f"  Exists ({mib:.1f} MiB), skipping: {dest.name}")
        return True
    print(f"Downloading {desc} …")
    print(f"  {url}")
    tmp = dest.with_suffix(".part")
    try:
        urllib.request.urlretrieve(url, tmp, reporthook=_progress)
        print()
        tmp.rename(dest)
        mib = dest.stat().st_size / (1024 * 1024)
        print(f"  Written: {dest.name} ({mib:.1f} MiB)")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"\n  FAILED: {exc}")
        if tmp.exists():
            tmp.unlink()
        return False


# ---------------------------------------------------------------------------
# Silesia corpus
# ---------------------------------------------------------------------------

SILESIA_URL = "http://sun.aei.polsl.pl/~sdeor/corpus/silesia.zip"


def download_silesia(fixtures_dir: Path, force: bool = False) -> bool:
    """Download and extract the Silesia corpus; create silesia_combined.bin."""
    silesia_dir = fixtures_dir / "silesia"
    combined = fixtures_dir / "silesia_combined.bin"

    if combined.exists() and not force:
        mib = combined.stat().st_size / (1024 * 1024)
        print(f"  Exists ({mib:.1f} MiB), skipping: silesia_combined.bin")
        return True

    zip_path = fixtures_dir / "silesia.zip"
    if not download(SILESIA_URL, zip_path, "Silesia corpus", force=force):
        return False

    print("Extracting Silesia corpus …")
    silesia_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.infolist():
                # Skip __MACOSX and directory entries
                if member.filename.startswith("__") or member.filename.endswith("/"):
                    continue
                # Extract to silesia/ using the bare filename (strip any sub-dirs)
                bare = Path(member.filename).name
                target = silesia_dir / bare
                with zf.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                print(f"  {target.name} ({target.stat().st_size // (1024 * 1024)} MiB)")
    except Exception as exc:  # noqa: BLE001
        print(f"  Extraction failed: {exc}")
        return False

    print("Creating silesia_combined.bin (concatenation of all corpus files) …")
    files = sorted(silesia_dir.iterdir())
    with open(combined, "wb") as out:
        for f in files:
            if f.is_file():
                out.write(f.read_bytes())
    mib = combined.stat().st_size / (1024 * 1024)
    print(f"  silesia_combined.bin ({mib:.0f} MiB) — {len(files)} files concatenated")
    return True


# ---------------------------------------------------------------------------
# Canterbury corpus
# ---------------------------------------------------------------------------

CANTERBURY_URL = "https://corpus.canterbury.ac.nz/resources/cantrbry.tar.gz"


def download_canterbury(fixtures_dir: Path, force: bool = False) -> bool:
    """Download and extract the Canterbury corpus."""
    cantrbry_dir = fixtures_dir / "cantrbry"
    sentinel = cantrbry_dir / "alice29.txt"

    if sentinel.exists() and not force:
        print("  Exists, skipping: Canterbury corpus (cantrbry/)")
        return True

    tar_path = fixtures_dir / "cantrbry.tar.gz"
    if not download(CANTERBURY_URL, tar_path, "Canterbury corpus", force=force):
        return False

    print("Extracting Canterbury corpus …")
    cantrbry_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(tar_path) as tf:
            tf.extractall(cantrbry_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"  Extraction failed: {exc}")
        return False

    files = list(cantrbry_dir.glob("*"))
    total = sum(f.stat().st_size for f in files if f.is_file())
    print(f"  cantrbry/  {len(files)} files, {total // 1024} KiB total")
    return True


# ---------------------------------------------------------------------------
# Big Buck Bunny video + audio
# ---------------------------------------------------------------------------

BBB_URL = (
    "https://download.blender.org/demo/movies/BBB/"
    "bbb_sunflower_720p_30fps_normal.mp4"
)
BBB_VIDEO_DURATION = 30   # seconds of FFV1 lossless clip
BBB_AUDIO_DURATION = 60   # seconds of PCM audio


def _run_ffmpeg(args: list[str], desc: str) -> bool:
    """Run an FFmpeg command.  Return True on success."""
    cmd = ["ffmpeg", "-y", "-loglevel", "warning"] + args
    print(f"  {desc}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  FFmpeg failed: {result.stderr[-500:]}")
        return False
    return True


def download_bbb(fixtures_dir: Path, force: bool = False) -> bool:
    """Download BBB 720p, extract a 30 s FFV1 clip and 60 s PCM audio."""
    video_clip = fixtures_dir / "bbb_720p_30s.mkv"
    audio_clip = fixtures_dir / "bbb_audio_60s.wav"

    if video_clip.exists() and audio_clip.exists() and not force:
        print(f"  Exists, skipping: {video_clip.name} + {audio_clip.name}")
        return True

    if shutil.which("ffmpeg") is None:
        print("  WARNING: ffmpeg not found on controller — skipping BBB fixtures.")
        print("           Install FFmpeg or run with --skip-video to suppress this.")
        return False

    bbb_mp4 = fixtures_dir / "bbb_sunflower_720p.mp4"
    if not download(BBB_URL, bbb_mp4, "Big Buck Bunny 720p (CC BY 3.0)", force=force):
        return False

    ok = True

    if not video_clip.exists() or force:
        print(f"Encoding {BBB_VIDEO_DURATION} s FFV1 lossless video clip …")
        ok = ok and _run_ffmpeg(
            [
                "-ss", "00:00:30",          # skip the production-card intro
                "-i", str(bbb_mp4),
                "-t", str(BBB_VIDEO_DURATION),
                "-c:v", "ffv1",
                "-level", "3",
                "-threads", "0",
                "-an",
                str(video_clip),
            ],
            f"ffmpeg → {video_clip.name}",
        )
        if video_clip.exists():
            mib = video_clip.stat().st_size / (1024 * 1024)
            print(f"  {video_clip.name} ({mib:.0f} MiB)")

    if not audio_clip.exists() or force:
        print(f"Extracting {BBB_AUDIO_DURATION} s PCM audio …")
        ok = ok and _run_ffmpeg(
            [
                "-ss", "00:00:30",
                "-i", str(bbb_mp4),
                "-t", str(BBB_AUDIO_DURATION),
                "-vn",
                "-c:a", "pcm_s16le",
                str(audio_clip),
            ],
            f"ffmpeg → {audio_clip.name}",
        )
        if audio_clip.exists():
            mib = audio_clip.stat().st_size / (1024 * 1024)
            print(f"  {audio_clip.name} ({mib:.1f} MiB)")

    return ok


# ---------------------------------------------------------------------------
# Kodak Lossless True Color Image Suite
# ---------------------------------------------------------------------------

KODAK_BASE = "http://r0k.us/graphics/kodak/kodak/"
KODAK_COUNT = 24


def download_kodak(fixtures_dir: Path, force: bool = False) -> bool:
    """Download all 24 Kodak reference images."""
    kodak_dir = fixtures_dir / "kodak"
    sentinel = kodak_dir / "kodim24.png"

    if sentinel.exists() and not force:
        print("  Exists, skipping: Kodak images (kodak/)")
        return True

    kodak_dir.mkdir(parents=True, exist_ok=True)
    ok = True
    downloaded = 0
    for n in range(1, KODAK_COUNT + 1):
        name = f"kodim{n:02d}.png"
        dest = kodak_dir / name
        url = KODAK_BASE + name
        if dest.exists() and not force:
            downloaded += 1
            continue
        print(f"Downloading Kodak image {n}/{KODAK_COUNT}: {name}")
        if download(url, dest, name, force=force):
            downloaded += 1
        else:
            ok = False

    total_mib = sum(
        f.stat().st_size for f in kodak_dir.glob("*.png") if f.is_file()
    ) / (1024 * 1024)
    print(f"  Kodak images: {downloaded}/{KODAK_COUNT} files, {total_mib:.1f} MiB total")
    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "fixtures_dir",
        type=Path,
        help="Output directory (e.g. benchmarks/fixtures/)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download and re-process all files even if they already exist.",
    )
    parser.add_argument(
        "--skip-video",
        action="store_true",
        help="Skip the Big Buck Bunny download (avoids ~330 MiB download).",
    )
    args = parser.parse_args()

    fixtures_dir: Path = args.fixtures_dir.resolve()
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    print(f"Fixture directory: {fixtures_dir}")

    results: dict[str, bool] = {}

    print("\n=== Silesia corpus ===")
    results["silesia"] = download_silesia(fixtures_dir, force=args.force)

    print("\n=== Canterbury corpus ===")
    results["canterbury"] = download_canterbury(fixtures_dir, force=args.force)

    if not args.skip_video:
        print("\n=== Big Buck Bunny (CC BY 3.0) ===")
        results["bbb"] = download_bbb(fixtures_dir, force=args.force)
    else:
        print("\n=== Big Buck Bunny — skipped (--skip-video) ===")
        results["bbb"] = False

    print("\n=== Kodak Lossless True Color Image Suite ===")
    results["kodak"] = download_kodak(fixtures_dir, force=args.force)

    print()
    failed = [k for k, v in results.items() if not v]
    if failed:
        print(f"WARNING: The following fixtures could not be downloaded: {', '.join(failed)}")
        print(
            "Benchmarks will fall back to synthetic data for missing fixtures.\n"
            "Re-run this script when connectivity is available, or see docs/benchmarks.md."
        )
        return 1

    print("All benchmark fixtures are ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
