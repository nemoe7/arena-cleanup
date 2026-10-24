"""The CLI is one standard-library file that runs on its own, with a Windows launcher."""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .conftest import ENGINE, ROOT, engine_version

LAUNCHER = ROOT / "arena-cleanup.cmd"


def test_the_cli_carries_its_own_version() -> None:
  assert re.fullmatch(r"\d+\.\d+\.\d+", engine_version())


def test_the_cli_imports_the_standard_library_only() -> None:
  tree = ast.parse(ENGINE.read_text())
  modules: set[str] = set()
  for node in ast.walk(tree):
    if isinstance(node, ast.Import):
      modules.update(alias.name.split(".")[0] for alias in node.names)
    elif isinstance(node, ast.ImportFrom) and node.module:
      modules.add(node.module.split(".")[0])
  assert modules <= sys.stdlib_module_names, modules - sys.stdlib_module_names


def test_the_cli_runs_alone_in_an_empty_directory(tmp_path: Path) -> None:
  # a PC gets the file and nothing else: no pyproject.toml, no ui/, no tests/
  copy = tmp_path / ENGINE.name
  shutil.copy(ENGINE, copy)
  res = subprocess.run(
    [sys.executable, str(copy), "-V"], capture_output=True, text=True, check=True
  )
  assert res.stdout.split() == ["arena-cleanup", engine_version()]


def test_the_launcher_runs_the_file_beside_it() -> None:
  text = LAUNCHER.read_bytes().decode()
  assert "\r\n" in text, "cmd.exe wants CRLF line endings"
  assert 'set "SCRIPT=%~dp0arena-cleanup.py"' in text
  assert '"%SCRIPT%" %*' in text
  assert "exit /b %ERRORLEVEL%" in text
  assert "py -3" in text and "python" in text
