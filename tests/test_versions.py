"""The version step check: a touched part steps once, an untouched part stays.

The engine constant sits in arena-cleanup.py, so a bump there is an engine
change by itself. The UI number sits outside ui/, so a bump without a UI
file change fails.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts import check_versions

BASE = (0, 1, 0)
STEPS_ABOVE_BASE = ((0, 1, 1), (0, 2, 0), (1, 0, 0))


def test_the_ui_version_comes_from_the_project_table() -> None:
  text = '[project]\nname = "x"\nversion = "1.2.3"\n'
  assert check_versions.version_of(text) == (1, 2, 3)
  with pytest.raises(ValueError, match="major.minor.patch"):
    check_versions.version_of('[project]\nversion = "1.2"\n')
  with pytest.raises(KeyError):
    check_versions.version_of('[tool]\nname = "x"\n')


def test_the_engine_version_comes_from_the_constant() -> None:
  text = 'PROG = "arena-cleanup"\n__version__ = "1.2.3"\n'
  assert check_versions.engine_version_of(text) == (1, 2, 3)
  with pytest.raises(ValueError, match="__version__"):
    check_versions.engine_version_of('PROG = "x"\n')


def test_one_step_means_patch_minor_or_major() -> None:
  assert check_versions.steps(BASE) == STEPS_ABOVE_BASE
  for off in (BASE, (0, 1, 2), (0, 2, 1), (1, 1, 0), (0, 0, 9)):
    assert off not in check_versions.steps(BASE)


def test_each_part_owns_its_files_only() -> None:
  ui, engine = check_versions.PARTS
  assert ui.owns("ui/static/index.html") and not ui.owns("arena-cleanup.py")
  assert engine.owns("arena-cleanup.py") and not engine.owns("ui/server.py")
  assert not any(part.owns("docs/design.md") for part in check_versions.PARTS)


def git(*argv: str, cwd: Path) -> None:
  identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
  subprocess.run(
    ["git", *identity, "-c", "commit.gpgsign=false", *argv],
    cwd=cwd,
    check=True,
    capture_output=True,
  )


def write(root: Path, ui: str, engine: str, extra: dict[str, str]) -> None:
  (root / "pyproject.toml").write_text(f'[project]\nname = "x"\nversion = "{ui}"\n')
  (root / "arena-cleanup.py").write_text(f'__version__ = "{engine}"\n')
  for path, text in extra.items():
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(text)


def repo_with(root: Path, ui: str, engine: str, extra: dict[str, str]) -> None:
  """A repo whose tag `base` holds 0.1.0 twice and HEAD the given state."""
  git("init", "-q", "-b", "main", cwd=root)
  write(root, "0.1.0", "0.1.0", {"ui/page.html": "a", "README.md": "a"})
  git("add", "-A", cwd=root)
  git("commit", "-q", "-m", "base", cwd=root)
  git("tag", "base", cwd=root)
  write(root, ui, engine, extra)
  git("add", "-A", cwd=root)
  git("commit", "-q", "--allow-empty", "-m", "head", cwd=root)


@pytest.mark.parametrize(
  ("ui", "engine", "extra", "code", "complaint"),
  [
    ("0.1.1", "0.1.0", {"ui/page.html": "b"}, 0, ""),
    ("0.1.0", "0.1.0", {"ui/page.html": "b"}, 1, "ui: the version must step"),
    ("0.1.1", "0.1.0", {}, 1, "ui: no ui file changed, keep 0.1.0"),
    ("0.1.0", "0.2.0", {}, 0, ""),
    ("0.1.0", "0.1.0", {"README.md": "b"}, 0, ""),
    ("0.1.0", "0.1.1", {"README.md": "b"}, 0, ""),
    ("0.1.1", "0.1.1", {"ui/page.html": "b"}, 0, ""),
    ("0.3.0", "0.1.0", {"ui/page.html": "b"}, 1, "ui: the version must step to one of"),
  ],
)
def test_a_touched_part_steps_and_an_untouched_part_stays(
  tmp_path: Path,
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  ui: str,
  engine: str,
  extra: dict[str, str],
  code: int,
  complaint: str,
) -> None:
  repo_with(tmp_path, ui, engine, extra)
  monkeypatch.chdir(tmp_path)
  assert check_versions.main(["--base", "base", "--head", "HEAD"]) == code
  out = capsys.readouterr()
  assert f"pyproject.toml: 0.1.0 -> {ui} (ui" in out.out
  assert f"arena-cleanup.py: 0.1.0 -> {engine} (engine" in out.out
  assert complaint in out.err
  assert (out.err == "") is (code == 0)


def test_a_missing_ref_fails_with_the_git_message(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
  repo_with(tmp_path, "0.1.0", "0.1.0", {})
  monkeypatch.chdir(tmp_path)
  assert check_versions.main(["--base", "nowhere", "--head", "HEAD"]) == 1
  out = capsys.readouterr()
  assert out.out == ""
  assert "nowhere" in out.err
