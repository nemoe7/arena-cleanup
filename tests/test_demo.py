"""The demo fixture holds every repo state the dashboard has to show."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import demo
from ui.server import Registry


def git(*argv: str, cwd: Path, env: dict[str, str]) -> str:
  res = subprocess.run(
    ["git", *argv], cwd=cwd, env=env, capture_output=True, text=True, check=True
  )
  return res.stdout.strip()


@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
  root = tmp_path_factory.mktemp("demo")
  with pytest.MonkeyPatch.context() as patch:
    patch.setenv("GH_TOKEN", "sandbox")  # the host's token must not leak into the demo
    return demo.build(root)


@pytest.fixture(scope="module")
def entries(env: dict[str, str]) -> dict[str, dict[str, object]]:
  return {entry["name"]: entry for entry in Registry(Path(env["ARENA_DATA"])).all()}


@pytest.fixture(scope="module")
def repos(entries: dict[str, dict[str, object]]) -> dict[str, Path]:
  return {name: Path(str(entry["path"])) for name, entry in entries.items()}


def arena_branches(work: Path, env: dict[str, str]) -> list[str]:
  refs = git(
    "for-each-ref",
    "--format=%(refname:short)",
    "refs/remotes/origin",
    cwd=work,
    env=env,
  )
  return [ref for ref in refs.splitlines() if ref.startswith("origin/arena/")]


def test_the_repos_are_url_clones_under_data(
  entries: dict[str, dict[str, object]], env: dict[str, str]
) -> None:
  assert sorted(entries) == sorted(name for name, _branches, _later in demo.REPOS)
  clones = Path(env["ARENA_DATA"]) / "repos"
  for name, entry in entries.items():
    assert entry["managed"] is True
    assert entry["source"] == f"{demo.PAGE_BASE}/{name}"
    assert Path(str(entry["path"])) == clones / name


def test_the_origins_answer_to_github_urls(
  repos: dict[str, Path], env: dict[str, str]
) -> None:
  for name, work in repos.items():
    page = f"{demo.PAGE_BASE}/{name}"
    assert git("config", "--get", "remote.origin.url", cwd=work, env=env) == page
    resolved = git("remote", "get-url", "origin", cwd=work, env=env)
    assert resolved.endswith(f"/origins/{name}.git")
    assert git("ls-remote", "--heads", "origin", "main", cwd=work, env=env)


def test_one_default_branch_moved_on_after_its_session(
  repos: dict[str, Path], env: dict[str, str]
) -> None:
  ahead = {
    name: int(
      git(
        "rev-list",
        "--count",
        f"{arena_branches(work, env)[0]}..origin/main",
        cwd=work,
        env=env,
      )
    )
    for name, work in repos.items()
  }
  behind = {
    name: int(git("rev-list", "--count", "HEAD..origin/main", cwd=work, env=env))
    for name, work in repos.items()
  }
  moved = [name for name, _branches, later in demo.REPOS if later]
  assert moved == ["infra-tools"]
  assert ahead == {name: len(demo.MAIN_LATER) if name in moved else 0 for name in repos}
  assert behind == ahead  # the clone has not pulled, so its card shows drift


def test_one_repo_keeps_two_arena_branches(
  repos: dict[str, Path], env: dict[str, str]
) -> None:
  counts = {name: len(arena_branches(work, env)) for name, work in repos.items()}
  assert counts == {name: len(branches) for name, branches, _later in demo.REPOS}
  assert sorted(counts.values()) == [1, 1, 1, 1, 2]
  two = next(work for work in repos.values() if len(arena_branches(work, env)) == 2)
  first, second = arena_branches(two, env)
  main = git("rev-parse", "origin/main", cwd=two, env=env)
  assert git("merge-base", first, second, cwd=two, env=env) == main
  assert git("rev-parse", first, cwd=two, env=env) != git(
    "rev-parse", second, cwd=two, env=env
  )
  assert git("rev-parse", "--abbrev-ref", "HEAD", cwd=two, env=env) == "main"


def test_the_environment_looks_like_a_live_install(env: dict[str, str]) -> None:
  assert "GH_TOKEN" not in env
  assert "GITHUB_TOKEN" not in env
  helpers = git(
    "config",
    "--global",
    "--get-all",
    "credential.https://github.com.helper",
    cwd=Path.cwd(),
    env=env,
  )
  assert "gh auth git-credential" in helpers
  stub = Path(env["HOME"]).parent / "bin" / "gh"
  res = subprocess.run(
    [str(stub), "auth", "status", "--json", "hosts"],
    capture_output=True,
    text=True,
    env=env,
    check=True,
  )
  assert json.loads(res.stdout)["hosts"]["github.com"][0]["login"] == demo.ME_NAME
