"""The dashboard Reload button fetches every origin before it draws the cards."""

from __future__ import annotations

import subprocess

import pytest

from scripts.walk import Demo, Walker

pytestmark = pytest.mark.e2e

CARD = ".repo-card:has-text('shop-web')"
BRANCH = "arena/late-branch"


def test_reload_fetches_a_branch_that_appeared_on_origin(
  desktop: Walker, demo: Demo
) -> None:
  # the page fetches once after the cached cards are on screen. A Reload that
  # lands during that fetch takes its result and fetches nothing itself
  with desktop.page.expect_response("**/api/fetch"):
    desktop.goto()
  desktop.page.wait_for_selector(f"{CARD} .arena-row")
  rows = desktop.page.locator(f"{CARD} .arena-row")
  before = rows.count()
  assert desktop.page.locator(f"{CARD} .arena-row:has-text('{BRANCH}')").count() == 0
  origin = demo.root / "origins" / "shop-web.git"
  subprocess.run(
    ["git", f"--git-dir={origin}", "update-ref", f"refs/heads/{BRANCH}", "main"],
    check=True,
  )
  # Reload fetches every origin before it redraws: hold on its answer, not a clock
  with desktop.page.expect_response("**/api/fetch"):
    desktop.page.click("#repos-refresh")
  desktop.page.wait_for_selector(f"{CARD} .arena-row:has-text('{BRANCH}')")
  assert rows.count() == before + 1
  assert desktop.page.eval_on_selector("#repos-refresh", "e => e.disabled") is False
