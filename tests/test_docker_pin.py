"""The Docker pin: the tip of main must be the tested commit, or one steering sync past it."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from .conftest import ROOT

WORKFLOW = ROOT / ".github" / "workflows" / "docker.yml"
STEERING = {".agents/skills/x/SKILL.md": "x", "ARENA.md": "rules", "AGENTS.md": "rules"}


def pin_script() -> str:
  """Shell of the `Pin tested commit` step, lifted out of the workflow."""
  text = WORKFLOW.read_text()
  start = text.index("- name: Pin tested commit")
  body = text[text.index("run: |", start) + len("run: |") :]
  lines = body.splitlines()[1:]
  indent = len(lines[0]) - len(lines[0].lstrip())
  block = []
  for line in lines:
    if line.strip() and not line.startswith(" " * indent):
      break
    block.append(line[indent:])
  return "\n".join(block)


def git(*argv: str, cwd: Path) -> str:
  identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
  return subprocess.run(
    ["git", *identity, "-c", "commit.gpgsign=false", *argv],
    cwd=cwd,
    check=True,
    capture_output=True,
    text=True,
  ).stdout.strip()


def commit(root: Path, files: dict[str, str], message: str) -> str:
  for path, body in files.items():
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(body)
  git("add", "-A", cwd=root)
  git("commit", "-q", "-m", message, cwd=root)
  return git("rev-parse", "HEAD", cwd=root)


def pin(clone: Path, expected: str) -> subprocess.CompletedProcess[str]:
  return subprocess.run(
    ["bash", "-c", pin_script()],
    cwd=clone,
    env={**os.environ, "EXPECTED": expected},
    capture_output=True,
    text=True,
    check=False,
  )


@pytest.fixture
def origin(tmp_path: Path) -> Path:
  root = tmp_path / "origin"
  root.mkdir()
  git("init", "-q", "-b", "main", cwd=root)
  commit(root, {"arena-cleanup.py": "v1", "ui/server.py": "v1"}, "code")
  return root


def clone(origin: Path, depth: int = 2) -> Path:
  target = origin.parent / f"clone-{depth}"
  subprocess.run(
    [
      "git",
      "clone",
      "-q",
      "--depth",
      str(depth),
      "-b",
      "main",
      f"file://{origin}",
      str(target),
    ],
    check=True,
    capture_output=True,
  )
  return target


def test_the_tested_tip_passes(origin: Path) -> None:
  tested = git("rev-parse", "HEAD", cwd=origin)
  assert pin(clone(origin), tested).returncode == 0


def test_one_steering_sync_past_the_tested_commit_passes(origin: Path) -> None:
  tested = git("rev-parse", "HEAD", cwd=origin)
  commit(origin, STEERING, "chore: clankers sync")
  result = pin(clone(origin), tested)
  assert result.returncode == 0, result.stderr
  assert f"steering files only since the tested {tested}" in result.stdout


def test_a_shipped_change_past_the_tested_commit_fails(origin: Path) -> None:
  tested = git("rev-parse", "HEAD", cwd=origin)
  commit(origin, {**STEERING, "ui/server.py": "v2"}, "feat: untested")
  result = pin(clone(origin), tested)
  assert result.returncode == 1
  assert "shipped changes" in result.stderr
  assert "ui/server.py" in result.stderr
  assert "ARENA.md" not in result.stderr
  assert ".agents" not in result.stderr


def test_a_tested_commit_beyond_the_depth_fails(origin: Path) -> None:
  tested = git("rev-parse", "HEAD", cwd=origin)
  commit(origin, {"ARENA.md": "one"}, "chore: clankers sync")
  commit(origin, {"ARENA.md": "two"}, "chore: clankers sync")
  result = pin(clone(origin), tested)
  assert result.returncode == 1
  assert f"does not contain the tested {tested}" in result.stderr


def test_the_checkout_fetches_two_commits() -> None:
  assert re.search(r"ref: main\n(\s+#.*\n)?\s+fetch-depth: 2\n", WORKFLOW.read_text())
