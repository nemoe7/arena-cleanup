"""The version step check: one step above the base, no more and no less."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts import check_versions

BASE = (0, 1, 0)
STEPS_ABOVE_BASE = ((0, 1, 1), (0, 2, 0), (1, 0, 0))


def test_the_version_comes_from_the_project_table() -> None:
  text = '[project]\nname = "x"\nversion = "1.2.3"\n'
  assert check_versions.version_of(text) == (1, 2, 3)
  with pytest.raises(ValueError, match="major.minor.patch"):
    check_versions.version_of('[project]\nversion = "1.2"\n')
  with pytest.raises(KeyError):
    check_versions.version_of('[tool]\nname = "x"\n')


def test_one_step_means_patch_minor_or_major() -> None:
  assert check_versions.steps(BASE) == STEPS_ABOVE_BASE
  for off in (BASE, (0, 1, 2), (0, 2, 1), (1, 1, 0), (0, 0, 9)):
    assert off not in check_versions.steps(BASE)


def git(*argv: str, cwd: Path) -> None:
  identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
  subprocess.run(
    ["git", *identity, "-c", "commit.gpgsign=false", *argv],
    cwd=cwd,
    check=True,
    capture_output=True,
  )


def repo_with(root: Path, versions: list[str]) -> None:
  """A repo whose tag `base` holds the first version and HEAD the last."""
  git("init", "-q", "-b", "main", cwd=root)
  for index, version in enumerate(versions):
    (root / "pyproject.toml").write_text(
      f'[project]\nname = "x"\nversion = "{version}"\n'
    )
    git("add", "pyproject.toml", cwd=root)
    git("commit", "-q", "--allow-empty", "-m", f"v{version}", cwd=root)
    if index == 0:
      git("tag", "base", cwd=root)


@pytest.mark.parametrize(
  ("head", "code"),
  [("0.1.1", 0), ("0.2.0", 0), ("1.0.0", 0), ("0.1.0", 1), ("0.3.0", 1), ("0.0.9", 1)],
)
def test_the_check_compares_head_with_the_base_tip(
  tmp_path: Path,
  monkeypatch: pytest.MonkeyPatch,
  capsys: pytest.CaptureFixture[str],
  head: str,
  code: int,
) -> None:
  repo_with(tmp_path, ["0.1.0", head])
  monkeypatch.chdir(tmp_path)
  assert check_versions.main(["--base", "base", "--head", "HEAD"]) == code
  out = capsys.readouterr()
  assert f"{check_versions.SOURCE}: {check_versions.dotted(BASE)} -> {head}" in out.out
  allowed = [check_versions.dotted(step) for step in STEPS_ABOVE_BASE]
  assert all(step in out.err for step in allowed) is (code == 1)


def test_a_missing_ref_fails_with_the_git_message(
  tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
  repo_with(tmp_path, ["0.1.0"])
  monkeypatch.chdir(tmp_path)
  assert check_versions.main(["--base", "nowhere", "--head", "HEAD"]) == 1
  out = capsys.readouterr()
  assert out.out == ""
  assert "nowhere" in out.err
