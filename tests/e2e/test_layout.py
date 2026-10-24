"""The repo view fits its window: two cards up top, and the log takes what remains."""

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
    runHead: box('#run-card .card-head'), optionsHead: box('#options-card .card-head'),
    phases: box('#phases'), optionsBody: box('#options'), firstOption: box('#opt-branch'),
    lastRule: parseFloat(getComputedStyle(q('#checks')).borderBottomWidth),
  };
}"""

ARENA_ROWS = """() => [...document.querySelectorAll('.row-btn.select')].map((row) => {
  const box = (el) => { const b = el.getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; };
  return { name: box(row.querySelector('.txt')), tail: box(row.querySelector('.tail')) };
})"""


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


def test_the_two_cards_align_head_to_foot(browser: Any, demo: Demo) -> None:
  seen = open_with_a_run(browser, demo, 1568, 775)
  assert seen["run"][3] == seen["options"][3], "the card bottoms meet"
  assert seen["runHead"][3] == seen["optionsHead"][3], "the heads share one height"
  assert seen["firstOption"][1] == seen["optionsBody"][1], "no gap above the first row"
  assert seen["phases"][1] == seen["optionsBody"][1], "the first rows share one line"
  assert seen["lastRule"] == 0, "no rule under the last option row"


def test_the_log_keeps_its_floor_and_the_page_still_stays_put(
  browser: Any, demo: Demo
) -> None:
  seen = open_with_a_run(browser, demo, 1201, 700)
  log_height = seen["log"][3] - seen["log"][1]
  assert log_height >= LOG_FLOOR
  assert seen["pageScroll"] == 0, "a window too short scrolls the column, not the page"


def test_the_sidebar_arena_rows_take_two_lines(browser: Any, demo: Demo) -> None:
  """The tail sits under the name on every row, never beside it, as the cards do."""
  context = browser.new_context(viewport={"width": 1568, "height": 775})
  try:
    walker = Walker(context, demo.url)
    walker.goto(600)
    walker.click(".repo-card:has-text('data-pipeline') .repo-ico", 800)
    rows = walker.page.evaluate(ARENA_ROWS)
  finally:
    context.close()
  assert len(rows) == 2, "the demo repo carries two arena branches"
  for row in rows:
    assert row["tail"][1] >= row["name"][3], "the tail starts below the name"
    assert row["tail"][0] == row["name"][0], "the tail lines up with the name"
