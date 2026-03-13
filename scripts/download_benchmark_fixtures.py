#!/usr/bin/env python3
"""Download standardised benchmark fixture files.

Downloads and prepares:

  - **Silesia corpus** (211 MiB, 12 files) — compression benchmarks
    http://sun.aei.polsl.pl/~sdeor/corpus/silesia.zip
  - **Canterbury corpus** (2.8 MiB, 18 files) — compression benchmarks
    https://corpus.canterbury.ac.nz/resources/cantrbry.tar.gz
  - **Big Buck Bunny 1080p clip** (≈30 s, FFV1 lossless + PCM audio) — FFmpeg benchmarks
    https://download.blender.org/demo/movies/BBB/bbb_sunflower_1080p_30fps_normal.mp4.zip
    © Blender Foundation, CC BY 3.0 — https://peach.blender.org/
  - **Kodak Lossless True Color Image Suite** (24 PNG, ≈18 MiB) — ImageMagick benchmarks
    http://r0k.us/graphics/kodak/kodak/kodimNN.png
  - **SQLite amalgamation** (≈8.5 MiB, single C translation unit) — compiler benchmarks
    https://www.sqlite.org/2026/sqlite-amalgamation-3520000.zip

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


def download(url: str, dest: Path, desc: str, force: bool = False) -> bool:
    """Download *url* to *dest*.  Return True on success."""
    if dest.exists() and not force:
        mib = dest.stat().st_size / (1024 * 1024)
        print(f"  Exists ({mib:.1f} MiB), skipping: {dest.name}")
        return True
    print(f"Downloading {desc} …")
    print(f"  {url}")
    tmp = dest.with_suffix(".part")
    # Some CDNs (e.g. Cloudflare protecting Blender downloads) return 403 for
    # the default Python-urllib user-agent; use a neutral browser-style string.
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            done = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total > 0:
                        pct = min(done * 100 // total, 100)
                        mb = done / (1024 * 1024)
                        tmb = total / (1024 * 1024)
                        progress_bar = "=" * (pct // 2) + ">" + " " * (50 - pct // 2)
                        print(f"\r  [{progress_bar}] {pct}%  {mb:.1f}/{tmb:.1f} MiB", end="", flush=True)
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
    "bbb_sunflower_1080p_30fps_normal.mp4.zip"
)
BBB_MP4_NAME = "bbb_sunflower_1080p_30fps_normal.mp4"
BBB_VIDEO_DURATION = 30   # seconds of FFV1 lossless clip
BBB_AUDIO_DURATION = 60   # seconds of PCM audio


def _run_ffmpeg(args: list[str], desc: str) -> bool:
    """Run an FFmpeg command.  Return True on success."""
    cmd = ["ffmpeg", "-y", "-loglevel", "warning"] + args
    print(f"  {desc}")
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(f"  FFmpeg failed: {result.stderr[-500:]}")
        return False
    return True


def download_bbb(fixtures_dir: Path, force: bool = False) -> bool:
    """Download BBB 1080p zip, extract the MP4, make FFV1 clip and PCM audio."""
    video_clip = fixtures_dir / "bbb_1080p_30s.mkv"
    audio_clip = fixtures_dir / "bbb_audio_60s.wav"

    if video_clip.exists() and audio_clip.exists() and not force:
        print(f"  Exists, skipping: {video_clip.name} + {audio_clip.name}")
        return True

    if shutil.which("ffmpeg") is None:
        print("  WARNING: ffmpeg not found on controller — skipping BBB fixtures.")
        print("           Install FFmpeg or run with --skip-video to suppress this.")
        return False

    bbb_zip = fixtures_dir / "bbb_sunflower_1080p.mp4.zip"
    if not download(BBB_URL, bbb_zip, "Big Buck Bunny 1080p (CC BY 3.0)", force=force):
        return False

    bbb_mp4 = fixtures_dir / BBB_MP4_NAME
    if not bbb_mp4.exists() or force:
        print(f"Extracting {BBB_MP4_NAME} from zip …")
        try:
            with zipfile.ZipFile(bbb_zip) as zf:
                members = [m for m in zf.namelist() if m.endswith(".mp4")]
                if not members:
                    print("  No MP4 found in zip.")
                    return False
                with zf.open(members[0]) as src, open(bbb_mp4, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            mib = bbb_mp4.stat().st_size / (1024 * 1024)
            print(f"  {bbb_mp4.name} ({mib:.0f} MiB)")
        except Exception as exc:  # noqa: BLE001
            print(f"  Extraction failed: {exc}")
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
# SQLite amalgamation
# ---------------------------------------------------------------------------

SQLITE_URL = "https://www.sqlite.org/2026/sqlite-amalgamation-3520000.zip"
SQLITE_ZIP_NAME = "sqlite-amalgamation-3520000.zip"


def download_sqlite_amalgamation(fixtures_dir: Path, force: bool = False) -> bool:
    """Download the SQLite amalgamation and extract sqlite3.c.

    The amalgamation is a single ~8.5 MiB C translation unit used by the
    compiler benchmarks to measure compile time on a realistic, non-trivial
    workload (gcc -O0 ~4–8 s, -O2 ~12–25 s, -O3 ~20–35 s).
    """
    dest = fixtures_dir / "sqlite3.c"

    if dest.exists() and not force:
        mib = dest.stat().st_size / (1024 * 1024)
        print(f"  Exists ({mib:.1f} MiB), skipping: sqlite3.c")
        return True

    zip_path = fixtures_dir / SQLITE_ZIP_NAME
    if not download(SQLITE_URL, zip_path, SQLITE_ZIP_NAME, force=force):
        return False

    print("  Extracting sqlite3.c from amalgamation zip …")
    try:
        with zipfile.ZipFile(zip_path) as zf:
            # The zip contains a directory; find sqlite3.c inside it
            names = [n for n in zf.namelist() if n.endswith("/sqlite3.c")]
            if not names:
                print("  ERROR: sqlite3.c not found in zip archive")
                return False
            member = names[0]
            with zf.open(member) as src, open(dest, "wb") as dst:
                dst.write(src.read())
    except Exception as exc:  # noqa: BLE001
        print(f"  ERROR extracting sqlite3.c: {exc}")
        return False

    zip_path.unlink(missing_ok=True)
    mib = dest.stat().st_size / (1024 * 1024)
    print(f"  SQLite amalgamation: sqlite3.c ({mib:.1f} MiB)")
    return True


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

    print("\n=== SQLite amalgamation ===")
    results["sqlite"] = download_sqlite_amalgamation(fixtures_dir, force=args.force)

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
