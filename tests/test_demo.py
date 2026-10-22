"""The demo fixture holds the repository states the dashboard has to show."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from scripts import demo


def git(*argv: str, cwd: Path) -> str:
  res = subprocess.run(
    ["git", *argv], cwd=cwd, capture_output=True, text=True, check=True
  )
  return res.stdout.strip()


@pytest.fixture(scope="module")
def repos(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
  root = tmp_path_factory.mktemp("demo")
  env = {**os.environ, "HOME": str(root), "GIT_CONFIG_GLOBAL": str(root / "gitconfig")}
  return {
    name: demo.make_repo(root, name, branches, later, env)
    for name, branches, later in demo.REPOS
  }


def arena_branches(work: Path) -> list[str]:
  refs = git(
    "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin", cwd=work
  )
  return [ref for ref in refs.splitlines() if ref.startswith("origin/arena/")]


def test_one_default_branch_moved_on_after_its_session(repos: dict[str, Path]) -> None:
  ahead = {
    name: int(
      git("rev-list", "--count", f"{arena_branches(work)[0]}..origin/main", cwd=work)
    )
    for name, work in repos.items()
  }
  behind = {
    name: int(git("rev-list", "--count", "HEAD..origin/main", cwd=work))
    for name, work in repos.items()
  }
  moved = [name for name, _branches, later in demo.REPOS if later]
  assert moved == ["infra-tools"]
  assert ahead == {name: len(demo.MAIN_LATER) if name in moved else 0 for name in repos}
  assert behind == ahead  # the clone has not pulled, so the card shows the drift


def test_one_repository_keeps_two_arena_branches(repos: dict[str, Path]) -> None:
  counts = {name: len(arena_branches(work)) for name, work in repos.items()}
  assert counts == {name: len(branches) for name, branches, _later in demo.REPOS}
  assert sorted(counts.values()) == [1, 1, 1, 1, 2]
  two = next(work for work in repos.values() if len(arena_branches(work)) == 2)
  first, second = arena_branches(two)
  assert git("merge-base", first, second, cwd=two) == git(
    "rev-parse", "origin/main", cwd=two
  )
  assert git("rev-parse", first, cwd=two) != git("rev-parse", second, cwd=two)
  assert git("rev-parse", "--abbrev-ref", "HEAD", cwd=two) == "main"
