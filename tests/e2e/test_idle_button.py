"""Clean & Push is disabled when no arena branch is ahead.

The default branch runs through an arena branch. With none ahead on origin
the dashboard card, repo view, and phone bar grey the button. Its
tooltip names the reason. The status refresh after a reload turns it back on.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator

import pytest

from scripts.walk import Demo, Walker

pytestmark = pytest.mark.e2e

REPO = "billing-api"
BRANCH = "arena/session-1"
CARD = f".repo-card:has-text('{REPO}')"
NO_WORK = "nothing to clean or push"
BUTTON = (
  "(b) => ({ disabled: b.disabled, title: b.title, state: b.dataset.state || null })"
)


@pytest.fixture
def branch_gone(demo: Demo) -> Iterator[None]:
  origin = demo.root / "origins" / f"{REPO}.git"
  git = ["git", f"--git-dir={origin}"]
  sha = subprocess.run(
    [*git, "rev-parse", f"refs/heads/{BRANCH}"],
    check=True,
    capture_output=True,
    text=True,
  ).stdout.strip()
  subprocess.run([*git, "update-ref", "-d", f"refs/heads/{BRANCH}"], check=True)
  try:
    yield
  finally:
    subprocess.run([*git, "update-ref", f"refs/heads/{BRANCH}", sha], check=True)


def reload_until(walker: Walker, text: str) -> None:
  walker.page.click("#repos-refresh")
  walker.page.wait_for_selector(f"{CARD} .arena-row:has-text('{text}')")


def check_idle(walker: Walker, idle: bool) -> None:
  page = walker.page
  card = page.locator(f"{CARD} .card-actions .btn").evaluate(BUTTON)
  assert card["disabled"] is idle, card
  assert (card["title"] == NO_WORK) is idle, card
  walker.click(f"{CARD} .repo-name", 800)
  page.wait_for_selector("#options-card")
  for sel in ("#start", "#start-mobile"):
    run = page.locator(sel).evaluate(BUTTON)
    assert run["state"] == "idle", run
    assert run["disabled"] is idle, run
    assert (run["title"] == NO_WORK) is idle, run
  walker.click("#back", 600)


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_the_button_rests_without_an_arena_branch(
  request: pytest.FixtureRequest, branch_gone: None, width: str
) -> None:
  walker: Walker = request.getfixturevalue(width)
  walker.goto(1200)
  walker.page.wait_for_selector(f"{CARD} .arena-row")
  reload_until(walker, "no arena/* branches")
  check_idle(walker, True)


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_the_button_wakes_when_a_branch_is_ahead(
  request: pytest.FixtureRequest, width: str
) -> None:
  walker: Walker = request.getfixturevalue(width)
  walker.goto(1200)
  reload_until(walker, BRANCH)
  check_idle(walker, False)
