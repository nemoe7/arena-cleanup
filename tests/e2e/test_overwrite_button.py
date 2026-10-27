"""Clean & Push greys when a clean would overwrite the default, or when nothing is ahead.

The default branch runs through the newest arena branch. With origin's default
past that branch or at its tip, card, repo view, and phone bar grey the button.
Its tooltip names the reason. With a branch ahead the button stays live.

Without an arena branch the run names the default branch. The button stays live
while that branch holds an unsigned commit, and greys once every commit carries
a signature (docs/design.md).
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator

import pytest

from scripts.walk import Demo, Walker

pytestmark = pytest.mark.e2e

REPO = "billing-api"
BRANCH = "arena/1b9d4c7e-billing-api"
CARD = f".repo-card:has-text('{REPO}')"
OVERWRITE = "a clean would overwrite commits on main"
BUTTON = (
  "(b) => ({ disabled: b.disabled, title: b.title, state: b.dataset.state || null })"
)
# a signature header as git stores one: the page checks its presence, not the key
SIGNATURE = b"gpgsig -----BEGIN PGP SIGNATURE-----\n \n iQEzBAABCAAdFiEE\n -----END PGP SIGNATURE-----"


def origin_git(demo: Demo) -> list[str]:
  return ["git", f"--git-dir={demo.root / 'origins' / f'{REPO}.git'}"]


def ref(git: list[str], name: str) -> str:
  return subprocess.run(
    [*git, "rev-parse", name], check=True, capture_output=True, text=True
  ).stdout.strip()


@pytest.fixture
def branch_gone(demo: Demo) -> Iterator[None]:
  git = origin_git(demo)
  sha = ref(git, f"refs/heads/{BRANCH}")
  subprocess.run([*git, "update-ref", "-d", f"refs/heads/{BRANCH}"], check=True)
  try:
    yield
  finally:
    subprocess.run([*git, "update-ref", f"refs/heads/{BRANCH}", sha], check=True)


@pytest.fixture
def default_moved(demo: Demo) -> Iterator[None]:
  """origin/main gains a commit past the arena tip, so the branch reads below 0."""
  git = origin_git(demo)
  main = ref(git, "refs/heads/main")
  tip = ref(git, f"refs/heads/{BRANCH}")
  who = {"GIT_AUTHOR_NAME": "Demo", "GIT_AUTHOR_EMAIL": "demo@example.com"}
  who |= {"GIT_COMMITTER_NAME": "Demo", "GIT_COMMITTER_EMAIL": "demo@example.com"}
  moved = subprocess.run(
    [*git, "commit-tree", f"{tip}^{{tree}}", "-p", tip, "-m", "chore: maintenance"],
    check=True,
    capture_output=True,
    text=True,
    env={**os.environ, **who},
  ).stdout.strip()
  subprocess.run([*git, "update-ref", "refs/heads/main", moved], check=True)
  try:
    yield
  finally:
    subprocess.run([*git, "update-ref", "refs/heads/main", main], check=True)


@pytest.fixture
def default_absorbed(demo: Demo) -> Iterator[None]:
  """origin/main moves to the arena tip, so the branch reads 0."""
  git = origin_git(demo)
  main = ref(git, "refs/heads/main")
  tip = ref(git, f"refs/heads/{BRANCH}")
  subprocess.run([*git, "update-ref", "refs/heads/main", tip], check=True)
  try:
    yield
  finally:
    subprocess.run([*git, "update-ref", "refs/heads/main", main], check=True)


def signed_copy(git: list[str], tip: str) -> str:
  """The history of `tip` rebuilt with a signature header on every commit."""
  new: dict[str, str] = {}
  order = subprocess.run(
    [*git, "rev-list", "--reverse", "--topo-order", tip],
    check=True,
    capture_output=True,
    text=True,
  ).stdout.split()
  for sha in order:
    raw = subprocess.run(
      [*git, "cat-file", "commit", sha], check=True, capture_output=True
    ).stdout
    head, message = raw.split(b"\n\n", 1)
    lines = []
    for line in head.split(b"\n"):
      if line.startswith(b"parent "):
        line = b"parent " + new[line[7:].decode()].encode()
      lines.append(line)
      if line.startswith(b"committer "):
        lines.append(SIGNATURE)
    new[sha] = (
      subprocess.run(
        [*git, "hash-object", "-t", "commit", "-w", "--stdin"],
        check=True,
        capture_output=True,
        input=b"\n".join(lines) + b"\n\n" + message,
      )
      .stdout.decode()
      .strip()
    )
  return new[tip]


@pytest.fixture
def history_signed(demo: Demo) -> Iterator[None]:
  """Every commit on origin's main carries a signature header: nothing is left to sign."""
  git = origin_git(demo)
  main = ref(git, "refs/heads/main")
  subprocess.run(
    [*git, "update-ref", "refs/heads/main", signed_copy(git, main)], check=True
  )
  try:
    yield
  finally:
    subprocess.run([*git, "update-ref", "refs/heads/main", main], check=True)


def refresh(walker: Walker) -> None:
  """Reload, and wait for the button to come back: the fetched list is on screen."""
  walker.page.click("#repos-refresh")
  walker.page.wait_for_function(
    "() => !document.getElementById('repos-refresh').disabled"
  )


def check_block(walker: Walker, reason: str) -> str:
  """Every Clean & Push greys with `reason`, or stays live with an empty one.

  Returns the command line of the repo view's run button.
  """
  page = walker.page
  card = page.locator(f"{CARD} .card-actions .btn").evaluate(BUTTON)
  assert card["disabled"] is bool(reason), card
  assert (card["title"] == reason) is bool(reason), card
  walker.click(f"{CARD} .repo-name")
  page.wait_for_selector("#options-card")
  for sel in ("#start", "#start-mobile"):
    run = page.locator(sel).evaluate(BUTTON)
    assert run["state"] == "idle", run
    assert run["disabled"] is bool(reason), run
    assert (run["title"] == reason) is bool(reason), run
  line = page.get_attribute("#start", "data-argv") or ""
  walker.click("#back")
  return line


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_the_button_rests_when_the_default_moved_past_the_branch(
  request: pytest.FixtureRequest, default_moved: None, width: str
) -> None:
  walker: Walker = request.getfixturevalue(width)
  walker.goto()
  refresh(walker)
  walker.page.wait_for_selector(f"{CARD} .arena-row .ahead", state="detached")
  check_block(walker, OVERWRITE)


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_the_button_rests_when_the_default_absorbed_the_branch(
  request: pytest.FixtureRequest, default_absorbed: None, width: str
) -> None:
  walker: Walker = request.getfixturevalue(width)
  walker.goto()
  refresh(walker)
  check_block(walker, f"nothing to clean on {BRANCH}")


def test_the_button_stays_live_without_an_arena_branch(
  desktop: Walker, branch_gone: None
) -> None:
  desktop.goto()
  desktop.page.wait_for_selector(f"{CARD} .arena-row")
  refresh(desktop)
  desktop.page.wait_for_selector(f"{CARD} .arena-row:has-text('no arena/* branches')")
  line = check_block(desktop, "")
  assert line.split()[:3] == ["run", "--branch", "main"], (
    "the run names the default branch"
  )


def test_the_button_rests_without_an_arena_branch_once_the_default_is_signed(
  desktop: Walker, branch_gone: None, history_signed: None
) -> None:
  desktop.goto()
  desktop.page.wait_for_selector(f"{CARD} .arena-row")
  refresh(desktop)
  desktop.page.wait_for_selector(f"{CARD} .arena-row:has-text('no arena/* branches')")
  check_block(desktop, "nothing to sign on main")


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_the_button_is_live_when_a_branch_is_ahead(
  request: pytest.FixtureRequest, width: str
) -> None:
  walker: Walker = request.getfixturevalue(width)
  walker.goto()
  refresh(walker)
  walker.page.wait_for_selector(f"{CARD} .arena-row:has(.bname[title='{BRANCH}'])")
  check_block(walker, "")
