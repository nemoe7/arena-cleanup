"""The header's loading bar marks the first repo list load.

A 30% fill sweeps the bar while the first list read runs, on the dashboard
alone. A fetch of the repo states spins the Reload glyph and shows no bar.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

PROGRESS = '{"active": true, "done": 3, "total": 10}'
BAR = """() => {
  const bar = document.getElementById('load-bar');
  const fill = bar.querySelector('i');
  return { hidden: bar.hidden, now: bar.getAttribute('aria-valuenow'),
    ratio: fill.getBoundingClientRect().width / bar.getBoundingClientRect().width,
    motion: getComputedStyle(fill).animationName,
    busy: document.getElementById('repos-refresh').getAttribute('aria-busy') };
}"""
BAR_HIDDEN = "document.getElementById('load-bar').hidden"


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_the_bar_sweeps_while_the_first_list_loads(
  request: pytest.FixtureRequest, width: str
) -> None:
  walker: Walker = request.getfixturevalue(width)
  page = walker.page
  held: list[Any] = []
  page.route("**/api/repos", lambda r: held.append(r))
  try:
    page.goto(walker.url, wait_until="load")
    page.wait_for_function(f"!{BAR_HIDDEN}")
    bar = page.evaluate(BAR)
    assert bar["now"] is None, "the list read has no counter, so no value"
    assert 0.29 < bar["ratio"] < 0.31, bar
    assert bar["motion"] == "sweep"
    assert bar["busy"] != "true", "the Reload glyph stays still"
    assert page.is_visible("#repo-loading"), "the text line stays with the bar"
  finally:
    for r in held:
      r.continue_()
    page.unroute("**/api/repos")
  page.wait_for_function(BAR_HIDDEN)
  page.wait_for_selector("#repo-loading", state="hidden")


def test_the_bar_belongs_to_the_dashboard(desktop: Walker) -> None:
  page = desktop.page
  held: list[Any] = []
  page.route("**/api/repos", lambda r: held.append(r))
  try:
    page.goto(desktop.url, wait_until="load")
    page.wait_for_function(f"!{BAR_HIDDEN}")
    page.click("#settings-btn")
    page.wait_for_selector("#view-settings", state="visible")
    assert page.evaluate(BAR)["hidden"] is True, "Settings hides it at once"
    page.click("#settings-back")
    page.wait_for_selector("#view-dashboard", state="visible")
    assert page.evaluate(BAR)["hidden"] is False, "the dashboard shows it again"
  finally:
    for r in held:
      r.continue_()
    page.unroute("**/api/repos")
  page.wait_for_function(BAR_HIDDEN)


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_a_fetch_spins_the_reload_glyph_without_the_bar(
  request: pytest.FixtureRequest, width: str
) -> None:
  walker: Walker = request.getfixturevalue(width)
  page = walker.page
  walker.goto(1200)
  assert page.evaluate(BAR)["hidden"] is True, "no bar at rest"
  held: list[Any] = []
  page.route("**/api/fetch", lambda r: held.append(r))
  page.route(
    "**/api/progress",
    lambda r: r.fulfill(status=200, content_type="application/json", body=PROGRESS),
  )
  try:
    page.click("#repos-refresh")
    page.wait_for_function(
      "document.getElementById('repos-refresh').getAttribute('aria-busy') === 'true'"
    )
    page.wait_for_timeout(900)
    bar = page.evaluate(BAR)
    assert bar["hidden"] is True, "a fetch of the repo states shows no bar"
    assert bar["busy"] == "true", "the Reload glyph spins"
  finally:
    for r in held:
      r.continue_()
    page.unroute("**/api/fetch")
    page.unroute("**/api/progress")
  page.wait_for_function(
    "document.getElementById('repos-refresh').getAttribute('aria-busy') === 'false'"
  )
  assert page.evaluate(BAR)["hidden"] is True
