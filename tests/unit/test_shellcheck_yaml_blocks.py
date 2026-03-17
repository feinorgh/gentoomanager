"""Unit tests for scripts/shellcheck_yaml_blocks.py."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import shellcheck_yaml_blocks as syb  # noqa: E402

# ---------------------------------------------------------------------------
# _preprocess_for_yaml
# ---------------------------------------------------------------------------


class TestPreprocessForYaml:
    def test_removes_jinja2_variable(self) -> None:
        result = syb._preprocess_for_yaml("- name: {{ my_var }}")
        assert "{{" not in result
        assert syb._PLACEHOLDER in result

    def test_removes_jinja2_block(self) -> None:
        result = syb._preprocess_for_yaml("{% if foo %}bar{% endif %}")
        assert "{%" not in result

    def test_removes_jinja2_comment(self) -> None:
        result = syb._preprocess_for_yaml("{# this is a comment #}")
        assert "{#" not in result

    def test_bare_word_placeholder_is_valid_yaml(self) -> None:
        content = "- name: task\n  shell: echo {{ var }}\n"
        safe = syb._preprocess_for_yaml(content)
        parsed = yaml.safe_load(safe)
        assert isinstance(parsed, list)

    def test_plain_text_unchanged(self) -> None:
        text = "plain text without jinja"
        assert syb._preprocess_for_yaml(text) == text

    def test_multiple_variables_replaced(self) -> None:
        result = syb._preprocess_for_yaml("{{ a }} and {{ b }}")
        assert "{{" not in result
        assert result.count(syb._PLACEHOLDER) == 2


# ---------------------------------------------------------------------------
# _strip_jinja2
# ---------------------------------------------------------------------------


class TestStripJinja2:
    def test_variable_replaced_with_placeholder(self) -> None:
        result = syb._strip_jinja2("echo {{ my_var }}")
        assert syb._PLACEHOLDER in result
        assert "{{" not in result

    def test_block_replaced_with_comment(self) -> None:
        result = syb._strip_jinja2("{% if foo %}\necho hi\n{% endif %}")
        assert "# j2:block" in result
        assert "{%" not in result

    def test_comment_replaced_with_comment(self) -> None:
        result = syb._strip_jinja2("{# note #}")
        assert "# j2:comment" in result
        assert "{#" not in result

    def test_stripped_script_is_syntactically_valid_shell(self) -> None:
        script = "if {{ condition }}; then\n  echo {{ msg }}\nfi"
        stripped = syb._strip_jinja2(script)
        assert "if" in stripped
        assert "fi" in stripped

    def test_no_jinja2_unchanged(self) -> None:
        script = "echo hello\nls -la\n"
        assert syb._strip_jinja2(script) == script

    def test_whitespace_control_dashes_removed(self) -> None:
        result = syb._strip_jinja2("{%- if foo -%}")
        assert "# j2:block" in result


# ---------------------------------------------------------------------------
# _extract_shell_content
# ---------------------------------------------------------------------------


class TestExtractShellContent:
    def test_shell_key_string(self) -> None:
        task = {"name": "t", "shell": "echo hi"}
        assert syb._extract_shell_content(task) == "echo hi"

    def test_ansible_builtin_shell_key(self) -> None:
        task = {"name": "t", "ansible.builtin.shell": "ls /tmp"}
        assert syb._extract_shell_content(task) == "ls /tmp"

    def test_win_shell_skipped(self) -> None:
        task = {"name": "t", "win_shell": "Get-Process"}
        assert syb._extract_shell_content(task) is None

    def test_ansible_windows_win_shell_skipped(self) -> None:
        task = {"name": "t", "ansible.windows.win_shell": "Get-Process"}
        assert syb._extract_shell_content(task) is None

    def test_command_key_ignored(self) -> None:
        task = {"name": "t", "command": "ls /tmp"}
        assert syb._extract_shell_content(task) is None

    def test_no_shell_key_returns_none(self) -> None:
        task = {"name": "t", "copy": {"src": "a", "dest": "b"}}
        assert syb._extract_shell_content(task) is None

    def test_shell_dict_with_cmd(self) -> None:
        task = {"name": "t", "shell": {"cmd": "echo hi"}}
        assert syb._extract_shell_content(task) == "echo hi"

    def test_shell_dict_with_raw_params(self) -> None:
        task = {"name": "t", "shell": {"_raw_params": "echo raw"}}
        assert syb._extract_shell_content(task) == "echo raw"


# ---------------------------------------------------------------------------
# extract_blocks
# ---------------------------------------------------------------------------


class TestExtractBlocks:
    def test_extracts_single_shell_task(self, tmp_path: Path) -> None:
        content = textwrap.dedent("""\
            - name: say hello
              shell: echo hello
        """)
        f = tmp_path / "tasks.yml"
        f.write_text(content)
        blocks = syb.extract_blocks(f)
        assert len(blocks) == 1
        name, script = blocks[0]
        assert name == "say hello"
        assert "echo hello" in script

    def test_skips_non_shell_tasks(self, tmp_path: Path) -> None:
        content = textwrap.dedent("""\
            - name: copy file
              copy:
                src: a
                dest: b
        """)
        f = tmp_path / "tasks.yml"
        f.write_text(content)
        assert syb.extract_blocks(f) == []

    def test_multiple_tasks_extracted(self, tmp_path: Path) -> None:
        content = textwrap.dedent("""\
            - name: first
              shell: echo one
            - name: second
              shell: echo two
        """)
        f = tmp_path / "tasks.yml"
        f.write_text(content)
        blocks = syb.extract_blocks(f)
        assert len(blocks) == 2

    def test_jinja2_stripped_from_shell_content(self, tmp_path: Path) -> None:
        content = textwrap.dedent("""\
            - name: with jinja
              shell: echo {{ my_var }}
        """)
        f = tmp_path / "tasks.yml"
        f.write_text(content)
        blocks = syb.extract_blocks(f)
        assert len(blocks) == 1
        _unused, script = blocks[0]
        assert "{{" not in script
        assert syb._PLACEHOLDER in script

    def test_unnamed_task_gets_default_name(self, tmp_path: Path) -> None:
        content = textwrap.dedent("""\
            - shell: echo hi
        """)
        f = tmp_path / "tasks.yml"
        f.write_text(content)
        blocks = syb.extract_blocks(f)
        assert len(blocks) == 1
        name, _unused = blocks[0]
        assert "unnamed" in name.lower()

    def test_nonexistent_file_returns_empty(self, tmp_path: Path) -> None:
        assert syb.extract_blocks(tmp_path / "missing.yml") == []

    def test_invalid_yaml_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.yml"
        f.write_text("{ invalid: yaml: content")
        assert syb.extract_blocks(f) == []

    def test_non_list_yaml_returns_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "dict.yml"
        f.write_text("key: value\n")
        assert syb.extract_blocks(f) == []

    def test_win_shell_tasks_skipped(self, tmp_path: Path) -> None:
        content = textwrap.dedent("""\
            - name: windows task
              win_shell: Get-Process
        """)
        f = tmp_path / "tasks.yml"
        f.write_text(content)
        assert syb.extract_blocks(f) == []


# ---------------------------------------------------------------------------
# collect_yaml_files
# ---------------------------------------------------------------------------


class TestCollectYamlFiles:
    def test_finds_yml_files_in_directory(self, tmp_path: Path) -> None:
        (tmp_path / "a.yml").write_text("")
        (tmp_path / "b.yaml").write_text("")
        (tmp_path / "c.txt").write_text("")
        files = syb.collect_yaml_files([tmp_path])
        names = {f.name for f in files}
        assert "a.yml" in names
        assert "b.yaml" in names
        assert "c.txt" not in names

    def test_single_file_path_accepted(self, tmp_path: Path) -> None:
        f = tmp_path / "tasks.yml"
        f.write_text("")
        files = syb.collect_yaml_files([f])
        assert f in files

    def test_excludes_venv_directory(self, tmp_path: Path) -> None:
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "something.yml").write_text("")
        (tmp_path / "real.yml").write_text("")
        files = syb.collect_yaml_files([tmp_path])
        names = {f.name for f in files}
        assert "real.yml" in names
        assert "something.yml" not in names

    def test_excludes_ansible_directory(self, tmp_path: Path) -> None:
        ans = tmp_path / ".ansible" / "cp"
        ans.mkdir(parents=True)
        (ans / "task.yml").write_text("")
        (tmp_path / "real.yml").write_text("")
        files = syb.collect_yaml_files([tmp_path])
        names = {f.name for f in files}
        assert "real.yml" in names
        assert "task.yml" not in names

    def test_empty_list_returns_empty(self) -> None:
        assert syb.collect_yaml_files([]) == []

    def test_nonexistent_path_ignored(self, tmp_path: Path) -> None:
        files = syb.collect_yaml_files([tmp_path / "missing"])
        assert files == []


# ---------------------------------------------------------------------------
# run_shellcheck
# ---------------------------------------------------------------------------


class TestRunShellcheck:
    def test_returns_completed_process(self) -> None:
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("shellcheck_yaml_blocks.subprocess.run", return_value=mock_result):
            result = syb.run_shellcheck("echo hi")
        assert result.returncode == 0

    def test_passes_shell_flag(self) -> None:
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 0
        with patch("shellcheck_yaml_blocks.subprocess.run", return_value=mock_result) as mock_run:
            syb.run_shellcheck("echo hi", shell="dash")
        cmd = mock_run.call_args[0][0]
        assert "--shell=dash" in cmd

    def test_sc2154_suppressed(self) -> None:
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 0
        with patch("shellcheck_yaml_blocks.subprocess.run", return_value=mock_result) as mock_run:
            syb.run_shellcheck("echo hi")
        cmd = mock_run.call_args[0][0]
        assert "-eSC2154" in cmd

    def test_nonzero_returncode_on_findings(self) -> None:
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 1
        mock_result.stdout = "SC2086: findings"
        with patch("shellcheck_yaml_blocks.subprocess.run", return_value=mock_result):
            result = syb.run_shellcheck("echo $unquoted")
        assert result.returncode == 1
