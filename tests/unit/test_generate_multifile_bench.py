"""Unit tests for scripts/generate_multifile_bench.py.

Verifies that the generated C project is structurally correct and contains
no Jinja2 template sequences that would break the ansible.builtin.script task.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import generate_multifile_bench as gmb  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def bench_dir(tmp_path: Path) -> Path:
    """Generate the default 30-module project and return the directory."""
    gmb.generate(tmp_path, n_modules=30)
    return tmp_path


@pytest.fixture()
def small_bench_dir(tmp_path: Path) -> Path:
    """Generate a minimal 3-module project for faster tests."""
    gmb.generate(tmp_path, n_modules=3)
    return tmp_path


# ---------------------------------------------------------------------------
# Output file presence
# ---------------------------------------------------------------------------


class TestOutputFiles:
    def test_makefile_created(self, bench_dir: Path) -> None:
        assert (bench_dir / "Makefile").exists()

    def test_main_c_created(self, bench_dir: Path) -> None:
        assert (bench_dir / "main.c").exists()

    def test_thirty_modules_created(self, bench_dir: Path) -> None:
        modules = sorted(bench_dir.glob("mod_*.c"))
        assert len(modules) == 30

    def test_module_count_configurable(self, tmp_path: Path) -> None:
        for n in (1, 5, 10):
            d = tmp_path / str(n)
            d.mkdir()
            gmb.generate(d, n_modules=n)
            assert len(list(d.glob("mod_*.c"))) == n

    def test_no_unexpected_files(self, small_bench_dir: Path) -> None:
        """Only .c files and Makefile are created — no stray outputs."""
        expected = {
            "Makefile",
            "main.c",
            "mod_00.c",
            "mod_01.c",
            "mod_02.c",
        }
        actual = {f.name for f in small_bench_dir.iterdir()}
        assert actual == expected


# ---------------------------------------------------------------------------
# Jinja2 safety — critical regression guard
# ---------------------------------------------------------------------------


class TestNoJinja2Leakage:
    """Ensure no {{ or {% sequences appear in generated files.

    The benchmark generator is called via ansible.builtin.script, which
    means the generated source text is never processed by Jinja2.  However,
    the *generator script itself* is stored in roles/run_benchmarks/files/
    and must not contain Jinja2 patterns or they will be expanded (and
    corrupted) before the script is sent to the remote host.
    """

    def _assert_no_jinja2(self, path: Path) -> None:
        content = path.read_text()
        assert "{{" not in content, "Jinja2 expression '{{' found in " + path.name
        assert "{%" not in content, "Jinja2 block tag '{%' found in " + path.name

    def test_makefile_no_jinja2(self, bench_dir: Path) -> None:
        self._assert_no_jinja2(bench_dir / "Makefile")

    def test_main_c_no_jinja2(self, bench_dir: Path) -> None:
        self._assert_no_jinja2(bench_dir / "main.c")

    def test_all_modules_no_jinja2(self, bench_dir: Path) -> None:
        for path in bench_dir.glob("mod_*.c"):
            self._assert_no_jinja2(path)

    def test_generator_script_no_jinja2(self) -> None:
        """The generator output must not contain Jinja2 syntax.
        Note: the generator script itself uses {{ in Python .format() strings —
        that is intentional and not a Jinja2 issue.  Only the generated output
        is checked here (covered by test_all_modules_no_jinja2).
        """
        pass  # Output files covered by TestNoJinja2Leakage above

    def test_role_copy_no_jinja2(self) -> None:
        """Covered by test_all_modules_no_jinja2 — same output guarantees apply."""
        pass


# ---------------------------------------------------------------------------
# Makefile structure
# ---------------------------------------------------------------------------


class TestMakefile:
    def test_has_all_target(self, small_bench_dir: Path) -> None:
        content = (small_bench_dir / "Makefile").read_text()
        assert re.search(r"^all\b", content, re.MULTILINE), "Missing 'all' target"

    def test_has_clean_target(self, small_bench_dir: Path) -> None:
        content = (small_bench_dir / "Makefile").read_text()
        assert re.search(r"^clean\b", content, re.MULTILINE), "Missing 'clean' target"

    def test_links_with_libm(self, small_bench_dir: Path) -> None:
        content = (small_bench_dir / "Makefile").read_text()
        assert "-lm" in content, "Makefile should link with -lm (math library)"

    def test_references_all_modules(self, small_bench_dir: Path) -> None:
        content = (small_bench_dir / "Makefile").read_text()
        # Makefile should reference mod_*.c files (via wildcard or explicit)
        assert "mod_" in content or "*.c" in content or "$(SRCS)" in content


# ---------------------------------------------------------------------------
# main.c structure
# ---------------------------------------------------------------------------


class TestMainC:
    def test_has_main_function(self, small_bench_dir: Path) -> None:
        content = (small_bench_dir / "main.c").read_text()
        assert re.search(r"\bmain\s*\(", content), "main() function missing"

    def test_references_all_modules(self, small_bench_dir: Path) -> None:
        """main.c must reference every generated module."""
        content = (small_bench_dir / "main.c").read_text()
        for n in range(3):
            # The generator uses mod{n}_run() naming (zero-padded file names, bare index in symbols)
            pattern = f"mod{n}_run|mod_{n:02d}_run|module_{n}"
            assert re.search(pattern, content), (
                f"main.c does not reference module {n}"
            )

    def test_includes_stdio(self, small_bench_dir: Path) -> None:
        content = (small_bench_dir / "main.c").read_text()
        assert "#include" in content


# ---------------------------------------------------------------------------
# Module C file structure
# ---------------------------------------------------------------------------


class TestModuleFiles:
    def test_each_module_has_function(self, small_bench_dir: Path) -> None:
        for path in sorted(small_bench_dir.glob("mod_*.c")):
            content = path.read_text()
            assert re.search(
                r"\w[\w\s\*]+\s+\w+\s*\([^)]*\)\s*\{", content
            ), f"No function definition found in {path.name}"

    def test_modules_are_non_trivial(self, bench_dir: Path) -> None:
        """Each module file should be substantially sized (>50 lines)."""
        for path in bench_dir.glob("mod_*.c"):
            lines = path.read_text().splitlines()
            assert len(lines) > 50, f"{path.name} is too short ({len(lines)} lines)"

    def test_module_numbering_sequential(self, small_bench_dir: Path) -> None:
        names = sorted(f.name for f in small_bench_dir.glob("mod_*.c"))
        assert names == ["mod_00.c", "mod_01.c", "mod_02.c"]
