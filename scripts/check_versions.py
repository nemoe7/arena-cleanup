"""Check that each touched part stepped its version once above the base branch.

Two parts carry a number: the UI in pyproject.toml and the engine in
arena-cleanup.py. A part whose files changed must step once, and a part left
alone must keep the base number. Any other file needs no bump.

The base tip's version counts, not the merge base's. Two open
branches can never claim the same number.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass

Version = tuple[int, int, int]
ENGINE_LINE = re.compile(r'^__version__ = "([^"]*)"$', re.MULTILINE)


def parse(raw: str) -> Version:
  """A major.minor.patch string as a tuple."""
  parts = raw.split(".")
  if len(parts) != 3 or not all(part.isdigit() for part in parts):
    raise ValueError(f"{raw!r} is not a major.minor.patch version")
  major, minor, patch = (int(part) for part in parts)
  return major, minor, patch


def version_of(text: str) -> Version:
  """The project version in a pyproject.toml text."""
  return parse(tomllib.loads(text)["project"]["version"])


def engine_version_of(text: str) -> Version:
  """The `__version__` constant in the engine source."""
  match = ENGINE_LINE.search(text)
  if not match:
    raise ValueError("no __version__ line")
  return parse(match.group(1))


@dataclass(frozen=True)
class Part:
  """One versioned part: where its number sits and which files belong to it."""

  name: str
  source: str
  read: Callable[[str], Version]
  paths: tuple[str, ...]

  def owns(self, path: str) -> bool:
    return any(path == own or path.startswith(own) for own in self.paths)


PARTS = (
  Part("ui", "pyproject.toml", version_of, ("ui/",)),
  Part("engine", "arena-cleanup.py", engine_version_of, ("arena-cleanup.py",)),
)
SOURCE = PARTS[0].source


def steps(before: Version) -> tuple[Version, Version, Version]:
  """The three versions one step above before: patch, minor, and major."""
  major, minor, patch = before
  return (major, minor, patch + 1), (major, minor + 1, 0), (major + 1, 0, 0)


def dotted(version: Version) -> str:
  """Format a version tuple."""
  return ".".join(str(part) for part in version)


def git(*args: str) -> str:
  """The output of a Git command."""
  return subprocess.run(
    ["git", *args], capture_output=True, text=True, check=True
  ).stdout


def changed(base: str, head: str) -> set[str]:
  """Paths the head changed since it left the base."""
  return set(git("diff", "--name-only", f"{base}...{head}").splitlines())


def check(part: Part, before: Version, after: Version, touched: bool) -> str | None:
  """The complaint for one part, or None when its number fits."""
  if touched and after not in steps(before):
    allowed = ", ".join(dotted(step) for step in steps(before))
    return f"{part.name}: the version must step to one of {allowed}"
  if not touched and after != before:
    return f"{part.name}: no {part.name} file changed, keep {dotted(before)}"
  return None


def main(argv: list[str] | None = None) -> int:
  """Compare each part's version at head with the one at base."""
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument(
    "--base",
    default="origin/main",
    help="the branch or commit the PR lands on",
  )
  parser.add_argument("--head", default="HEAD", help="the branch or commit under check")
  args = parser.parse_args(argv)
  try:
    files = changed(args.base, args.head)
    pairs = [
      (
        part,
        part.read(git("show", f"{args.base}:{part.source}")),
        part.read(git("show", f"{args.head}:{part.source}")),
      )
      for part in PARTS
    ]
  except (OSError, subprocess.CalledProcessError, KeyError, ValueError) as error:
    detail = (getattr(error, "stderr", None) or str(error)).strip()
    print(f"version read failed: {detail}", file=sys.stderr)
    return 1
  failed = False
  for part, before, after in pairs:
    touched = any(part.owns(path) for path in files)
    state = "changed" if touched else "untouched"
    print(f"{part.source}: {dotted(before)} -> {dotted(after)} ({part.name} {state})")
    complaint = check(part, before, after, touched)
    if complaint:
      print(complaint, file=sys.stderr)
      failed = True
  return int(failed)


if __name__ == "__main__":
  sys.exit(main())
