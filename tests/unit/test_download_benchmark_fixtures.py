"""Unit tests for scripts/download_benchmark_fixtures.py.

Tests URL constants, sentinel-file skip logic, and extraction helpers
using unittest.mock to avoid any real HTTP traffic.
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import download_benchmark_fixtures as dbf  # noqa: E402

# ---------------------------------------------------------------------------
# URL constant sanity checks
# ---------------------------------------------------------------------------


class TestUrlConstants:
    """Verify that fixture URLs are well-formed and point to the right hosts."""

    def test_silesia_url_is_http(self) -> None:
        assert dbf.SILESIA_URL.startswith("http")
        assert "silesia" in dbf.SILESIA_URL.lower()

    def test_canterbury_url_is_https(self) -> None:
        assert dbf.CANTERBURY_URL.startswith("https://")
        assert "canterbury" in dbf.CANTERBURY_URL

    def test_kodak_base_url(self) -> None:
        assert dbf.KODAK_BASE.startswith("http")
        assert dbf.KODAK_BASE.endswith("/")

    def test_kodak_count(self) -> None:
        assert dbf.KODAK_COUNT == 24

    def test_sqlite_url_points_to_sqlite_org(self) -> None:
        assert "sqlite.org" in dbf.SQLITE_URL
        assert dbf.SQLITE_URL.endswith(".zip")

    def test_sqlite_url_contains_version(self) -> None:
        # URL should contain a numeric version string
        import re

        assert re.search(r"\d{7}", dbf.SQLITE_URL), (
            "SQLite URL should contain a 7-digit version number"
        )

    def test_kodak_image_urls_are_correct(self) -> None:
        """Verify the 24 Kodak image URLs follow the expected pattern."""
        for n in range(1, dbf.KODAK_COUNT + 1):
            url = dbf.KODAK_BASE + f"kodim{n:02d}.png"
            assert url.endswith(".png")
            assert f"kodim{n:02d}" in url


# ---------------------------------------------------------------------------
# Sentinel / skip-if-exists logic
# ---------------------------------------------------------------------------


class TestSkipIfExists:
    """Each download function returns True immediately if the sentinel exists."""

    def test_silesia_skips_when_combined_exists(self, tmp_path: Path) -> None:
        combined = tmp_path / "silesia_combined.bin"
        combined.write_bytes(b"x")
        with patch.object(dbf, "download") as mock_dl:
            result = dbf.download_silesia(tmp_path, force=False)
        assert result is True
        mock_dl.assert_not_called()

    def test_silesia_redownloads_with_force(self, tmp_path: Path) -> None:
        combined = tmp_path / "silesia_combined.bin"
        combined.write_bytes(b"x")
        with patch.object(dbf, "download", return_value=False) as mock_dl:
            dbf.download_silesia(tmp_path, force=True)
        mock_dl.assert_called_once()

    def test_kodak_skips_when_sentinel_exists(self, tmp_path: Path) -> None:
        kodak_dir = tmp_path / "kodak"
        kodak_dir.mkdir()
        sentinel = kodak_dir / "kodim24.png"
        sentinel.write_bytes(b"PNG")
        with patch.object(dbf, "download") as mock_dl:
            result = dbf.download_kodak(tmp_path, force=False)
        assert result is True
        mock_dl.assert_not_called()

    def test_kodak_redownloads_with_force(self, tmp_path: Path) -> None:
        kodak_dir = tmp_path / "kodak"
        kodak_dir.mkdir()
        sentinel = kodak_dir / "kodim24.png"
        sentinel.write_bytes(b"PNG")
        with patch.object(dbf, "download", return_value=True) as mock_dl:
            dbf.download_kodak(tmp_path, force=True)
        # Should try to download all 24 images
        assert mock_dl.call_count == dbf.KODAK_COUNT

    def test_sqlite_skips_when_c_exists(self, tmp_path: Path) -> None:
        sqlite_c = tmp_path / "sqlite3.c"
        sqlite_c.write_bytes(b"/* sqlite */")
        with patch.object(dbf, "download") as mock_dl:
            result = dbf.download_sqlite_amalgamation(tmp_path, force=False)
        assert result is True
        mock_dl.assert_not_called()

    def test_sqlite_redownloads_with_force(self, tmp_path: Path) -> None:
        sqlite_c = tmp_path / "sqlite3.c"
        sqlite_c.write_bytes(b"/* sqlite */")
        with patch.object(dbf, "download", return_value=False) as mock_dl:
            dbf.download_sqlite_amalgamation(tmp_path, force=True)
        mock_dl.assert_called_once()

    def test_canterbury_skips_when_corpus_exists(self, tmp_path: Path) -> None:
        cant_dir = tmp_path / "cantrbry"
        cant_dir.mkdir()
        sentinel = cant_dir / "alice29.txt"
        sentinel.write_bytes(b"Alice")
        with patch.object(dbf, "download") as mock_dl:
            result = dbf.download_canterbury(tmp_path, force=False)
        assert result is True
        mock_dl.assert_not_called()


# ---------------------------------------------------------------------------
# Kodak URL construction
# ---------------------------------------------------------------------------


class TestKodakDownload:
    def test_downloads_all_24_images_when_none_exist(self, tmp_path: Path) -> None:
        with patch.object(dbf, "download", return_value=True) as mock_dl:
            dbf.download_kodak(tmp_path, force=False)
        assert mock_dl.call_count == dbf.KODAK_COUNT

    def test_skips_existing_images(self, tmp_path: Path) -> None:
        kodak_dir = tmp_path / "kodak"
        kodak_dir.mkdir()
        # Pre-create images 1-10
        for n in range(1, 11):
            (kodak_dir / f"kodim{n:02d}.png").write_bytes(b"PNG")
        with patch.object(dbf, "download", return_value=True) as mock_dl:
            dbf.download_kodak(tmp_path, force=False)
        # Only 14 remaining images should be downloaded
        assert mock_dl.call_count == 14

    def test_correct_urls_used(self, tmp_path: Path) -> None:
        called_urls: list[str] = []

        def capture_url(url: str, dest: Path, desc: str, **kwargs: object) -> bool:
            called_urls.append(url)
            return True

        with patch.object(dbf, "download", side_effect=capture_url):
            dbf.download_kodak(tmp_path, force=True)

        assert len(called_urls) == 24
        for n, url in enumerate(called_urls, start=1):
            assert url == dbf.KODAK_BASE + f"kodim{n:02d}.png"

    def test_returns_false_on_download_failure(self, tmp_path: Path) -> None:
        with patch.object(dbf, "download", return_value=False):
            result = dbf.download_kodak(tmp_path, force=True)
        assert result is False


# ---------------------------------------------------------------------------
# SQLite amalgamation extraction
# ---------------------------------------------------------------------------


class TestSqliteAmalgamation:
    def _make_sqlite_zip(self, tmp_path: Path) -> Path:
        """Create a minimal fake SQLite amalgamation zip."""
        zip_path = tmp_path / dbf.SQLITE_ZIP_NAME
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "sqlite-amalgamation-3520000/sqlite3.c",
                "/* fake sqlite3.c */\nint sqlite3_version = 3052000;\n",
            )
            zf.writestr(
                "sqlite-amalgamation-3520000/sqlite3.h",
                "/* fake header */\n",
            )
        zip_path.write_bytes(buf.getvalue())
        return zip_path

    def test_extracts_sqlite3_c(self, tmp_path: Path) -> None:
        self._make_sqlite_zip(tmp_path)

        def fake_download(url: str, dest: Path, desc: str, **kwargs: object) -> bool:
            # The download function is called to fetch the zip; simulate it
            # having already been placed by _make_sqlite_zip
            return True

        with patch.object(dbf, "download", side_effect=fake_download):
            result = dbf.download_sqlite_amalgamation(tmp_path, force=True)

        assert result is True
        assert (tmp_path / "sqlite3.c").exists()
        assert "fake sqlite3.c" in (tmp_path / "sqlite3.c").read_text()

    def test_zip_cleaned_up_after_extraction(self, tmp_path: Path) -> None:
        self._make_sqlite_zip(tmp_path)
        with patch.object(dbf, "download", return_value=True):
            dbf.download_sqlite_amalgamation(tmp_path, force=True)
        assert not (tmp_path / dbf.SQLITE_ZIP_NAME).exists()

    def test_returns_false_when_sqlite3_c_missing_in_zip(self, tmp_path: Path) -> None:
        zip_path = tmp_path / dbf.SQLITE_ZIP_NAME
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("sqlite-amalgamation-3520000/sqlite3.h", "/* header only */\n")
        zip_path.write_bytes(buf.getvalue())
        with patch.object(dbf, "download", return_value=True):
            result = dbf.download_sqlite_amalgamation(tmp_path, force=True)
        assert result is False

    def test_returns_false_when_download_fails(self, tmp_path: Path) -> None:
        with patch.object(dbf, "download", return_value=False):
            result = dbf.download_sqlite_amalgamation(tmp_path, force=True)
        assert result is False


# ---------------------------------------------------------------------------
# _run_ffmpeg
# ---------------------------------------------------------------------------


class TestRunFfmpeg:
    def test_returns_true_on_success(self) -> None:
        mock_result = type("R", (), {"returncode": 0, "stderr": ""})()
        with patch("download_benchmark_fixtures.subprocess.run", return_value=mock_result):
            result = dbf._run_ffmpeg(["-version"], "test")
        assert result is True

    def test_returns_false_on_nonzero_exit(self) -> None:
        mock_result = type("R", (), {"returncode": 1, "stderr": "error"})()
        with patch("download_benchmark_fixtures.subprocess.run", return_value=mock_result):
            result = dbf._run_ffmpeg(["-bad-flag"], "test")
        assert result is False

    def test_prepends_ffmpeg_y_loglevel(self) -> None:
        mock_result = type("R", (), {"returncode": 0, "stderr": ""})()
        with patch(
            "download_benchmark_fixtures.subprocess.run", return_value=mock_result
        ) as mock_run:
            dbf._run_ffmpeg(["-i", "input.mkv", "output.mkv"], "encode")
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "ffmpeg"
        assert "-y" in cmd
        assert "-loglevel" in cmd
        assert "warning" in cmd
        assert "-i" in cmd

    def test_prints_description(self, capsys) -> None:
        mock_result = type("R", (), {"returncode": 0, "stderr": ""})()
        with patch("download_benchmark_fixtures.subprocess.run", return_value=mock_result):
            dbf._run_ffmpeg([], "my description")
        out = capsys.readouterr().out
        assert "my description" in out


# ---------------------------------------------------------------------------
# download_bbb
# ---------------------------------------------------------------------------


class TestDownloadBbb:
    def test_skips_when_both_files_exist(self, tmp_path: Path) -> None:
        (tmp_path / "bbb_1080p_30s.mkv").write_text("video")
        (tmp_path / "bbb_audio_60s.wav").write_text("audio")
        with patch.object(dbf, "download") as mock_dl:
            result = dbf.download_bbb(tmp_path, force=False)
        assert result is True
        mock_dl.assert_not_called()

    def test_returns_false_when_ffmpeg_missing(self, tmp_path: Path) -> None:
        with patch("download_benchmark_fixtures.shutil.which", return_value=None):
            result = dbf.download_bbb(tmp_path)
        assert result is False

    def test_returns_false_when_download_fails(self, tmp_path: Path) -> None:
        with patch("download_benchmark_fixtures.shutil.which", return_value="/usr/bin/ffmpeg"):
            with patch.object(dbf, "download", return_value=False):
                result = dbf.download_bbb(tmp_path)
        assert result is False

    def test_force_flag_bypasses_skip(self, tmp_path: Path) -> None:
        (tmp_path / "bbb_1080p_30s.mkv").write_text("video")
        (tmp_path / "bbb_audio_60s.wav").write_text("audio")
        with patch("download_benchmark_fixtures.shutil.which", return_value="/usr/bin/ffmpeg"):
            with patch.object(dbf, "download", return_value=False):
                result = dbf.download_bbb(tmp_path, force=True)
        assert result is False


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


class TestMain:
    def test_returns_0_when_all_succeed(self, tmp_path: Path) -> None:
        rc = _call_main(tmp_path)
        assert rc == 0

    def test_returns_1_when_any_fails(self, tmp_path: Path) -> None:
        rc = _call_main(tmp_path, silesia=False)
        assert rc == 1

    def test_skip_video_skips_bbb(self, tmp_path: Path) -> None:
        with patch.object(dbf, "download_bbb") as mock_bbb:
            _call_main(tmp_path, skip_video=True)
        mock_bbb.assert_not_called()

    def test_all_five_fixtures_attempted_by_default(self, tmp_path: Path) -> None:
        with (
            patch.object(dbf, "download_silesia", return_value=True) as s,
            patch.object(dbf, "download_canterbury", return_value=True) as c,
            patch.object(dbf, "download_bbb", return_value=True) as b,
            patch.object(dbf, "download_kodak", return_value=True) as k,
            patch.object(dbf, "download_sqlite_amalgamation", return_value=True) as q,
            patch("sys.argv", ["prog", str(tmp_path)]),
        ):
            dbf.main()
        s.assert_called_once()
        c.assert_called_once()
        b.assert_called_once()
        k.assert_called_once()
        q.assert_called_once()


def _call_main(
    tmp_path: Path,
    silesia: bool = True,
    canterbury: bool = True,
    bbb: bool = True,
    kodak: bool = True,
    sqlite: bool = True,
    skip_video: bool = False,
) -> int:
    """Helper to call main() with patched download functions."""
    argv = [str(tmp_path)]
    if skip_video:
        argv.append("--skip-video")
    with (
        patch.object(dbf, "download_silesia", return_value=silesia),
        patch.object(dbf, "download_canterbury", return_value=canterbury),
        patch.object(dbf, "download_bbb", return_value=bbb),
        patch.object(dbf, "download_kodak", return_value=kodak),
        patch.object(dbf, "download_sqlite_amalgamation", return_value=sqlite),
        patch("sys.argv", ["prog"] + argv),
    ):
        return dbf.main()
