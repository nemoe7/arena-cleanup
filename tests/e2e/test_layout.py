"""The repo view fits the window: two cards up top, the log takes the rest."""

from __future__ import annotations

from typing import Any

import pytest

from scripts.walk import Demo, Walker

pytestmark = pytest.mark.e2e

CARD = ".repo-card:has-text('shop-web') .repo-ico"
LOG_FLOOR = 160
PROBE = """() => {
  const q = (s) => document.querySelector(s);
  const box = (s) => { const b = q(s).getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; };
  const col = q('.main-col');
  return {
    pageScroll: document.documentElement.scrollHeight - innerHeight,
    columnScroll: col.scrollHeight - col.clientHeight,
    run: box('#run-card'), options: box('#options-card'), log: box('#log'),
    logOverflow: q('#log').scrollHeight - q('#log').clientHeight,
    height: innerHeight,
  };
}"""


def open_with_a_run(
  browser: Any, demo: Demo, width: int, height: int
) -> dict[str, Any]:
  context = browser.new_context(viewport={"width": width, "height": height})
  try:
    walker = Walker(context, demo.url)
    walker.goto(600)
    walker.click(CARD, 800)
    walker.click('input[data-opt="dry_run"]', 0)
    walker.click("#start", 0)
    walker.wait_status("exit")
    walker.page.wait_for_timeout(300)
    return walker.page.evaluate(PROBE)
  finally:
    context.close()


def test_a_short_desktop_window_scrolls_the_log_alone(browser: Any, demo: Demo) -> None:
  seen = open_with_a_run(browser, demo, 1568, 775)
  assert seen["pageScroll"] == 0, "the page does not scroll"
  assert seen["columnScroll"] == 0, "nor does the main column"
  assert seen["run"][2] <= seen["options"][0], "the run card sits left of the options"
  assert seen["run"][1] == seen["options"][1], "both cards start on one line"
  assert seen["log"][1] >= max(seen["run"][3], seen["options"][3]), (
    "the log sits below both"
  )
  assert seen["log"][3] <= seen["height"], "the log ends inside the window"
  assert seen["logOverflow"] > 0, "a run log longer than its box scrolls inside it"


def test_the_log_keeps_its_floor_and_the_page_still_stays_put(
  browser: Any, demo: Demo
) -> None:
  seen = open_with_a_run(browser, demo, 1201, 700)
  log_height = seen["log"][3] - seen["log"][1]
  assert log_height >= LOG_FLOOR
  assert seen["pageScroll"] == 0, "a window too short scrolls the column, not the page"
