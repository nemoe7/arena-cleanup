"""Check that the project version is one step above the base branch.

The version at the base tip counts, not the one at the merge base. Two open
branches can never claim the same number.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib

SOURCE = "pyproject.toml"
Version = tuple[int, int, int]


def version_of(text: str) -> Version:
  """The project version in a pyproject.toml text, as a tuple."""
  raw = tomllib.loads(text)["project"]["version"]
  parts = raw.split(".")
  if len(parts) != 3 or not all(part.isdigit() for part in parts):
    raise ValueError(f"{raw!r} is not a major.minor.patch version")
  major, minor, patch = (int(part) for part in parts)
  return major, minor, patch


def steps(before: Version) -> tuple[Version, Version, Version]:
  """The three versions one step above before: patch, minor, and major."""
  major, minor, patch = before
  return (major, minor, patch + 1), (major, minor + 1, 0), (major + 1, 0, 0)


def dotted(version: Version) -> str:
  """Format a version tuple."""
  return ".".join(str(part) for part in version)


def show(ref: str, path: str) -> str:
  """The text of a file at a Git ref."""
  return subprocess.run(
    ["git", "show", f"{ref}:{path}"], capture_output=True, text=True, check=True
  ).stdout


def main(argv: list[str] | None = None) -> int:
  """Compare the project version at head with the one at base."""
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument(
    "--base",
    default="origin/main",
    help="the branch or commit the pull request lands on",
  )
  parser.add_argument("--head", default="HEAD", help="the branch or commit under check")
  args = parser.parse_args(argv)
  try:
    before = version_of(show(args.base, SOURCE))
    after = version_of(show(args.head, SOURCE))
  except (OSError, subprocess.CalledProcessError, KeyError, ValueError) as error:
    detail = (getattr(error, "stderr", None) or str(error)).strip()
    print(f"version read failed: {detail}", file=sys.stderr)
    return 1
  print(f"{SOURCE}: {dotted(before)} -> {dotted(after)}")
  if after in steps(before):
    return 0
  allowed = ", ".join(dotted(step) for step in steps(before))
  print(f"the version must step to one of {allowed}", file=sys.stderr)
  return 1


if __name__ == "__main__":
  raise SystemExit(main())
