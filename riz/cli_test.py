"""Exercise the installed command and module entry point as real processes."""

from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("command", [["riz"], [sys.executable, "-m", "riz"]])
def test_script_entry_points(command: list[str], tmp_path: Path):
    script = tmp_path / "example.riz"
    _ = script.write_text("fn half(n): n / 2\nhalf(5)\n", encoding="utf-8")
    result = subprocess.run([*command, str(script)], capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("source", "error"),
    [
        ("1 +", "RizParseError"),
        ("True + 1", "RizTypeError"),
        ("1 / 0", "RizDivisionByZeroError"),
    ],
)
def test_script_errors(source: str, error: str, tmp_path: Path):
    script = tmp_path / "bad.riz"
    _ = script.write_text(source, encoding="utf-8")
    result = subprocess.run(["riz", str(script)], capture_output=True, text=True)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == f"{script}: error: {error}\n"


@pytest.mark.parametrize("source", ["", " \n", "answer = 42\n", "()\n"])
def test_unit_scripts_are_silent(source: str, tmp_path: Path):
    script = tmp_path / "silent.riz"
    _ = script.write_text(source, encoding="utf-8")
    result = subprocess.run(["riz", str(script)], capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""


@pytest.mark.parametrize("contents", [None, b"\xff"])
def test_unreadable_script(contents: bytes | None, tmp_path: Path):
    script = tmp_path / "unreadable.riz"
    if contents is not None:
        _ = script.write_bytes(contents)
    result = subprocess.run(["riz", str(script)], capture_output=True, text=True)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith(f"{script}: error: ")
    assert "Traceback" not in result.stderr


def test_no_file_opens_repl():
    result = subprocess.run(
        ["riz"], input="2 + 3\nexit\n", capture_output=True, text=True
    )
    assert result.returncode == 0
    assert result.stdout == "riz> 5\nriz> "
    assert result.stderr == ""


def test_extra_arguments_are_rejected():
    result = subprocess.run(
        ["riz", "one.riz", "two.riz"], capture_output=True, text=True
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "unrecognized arguments" in result.stderr
