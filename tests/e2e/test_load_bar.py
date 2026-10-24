"""The header's loading bar follows the fetch counter.

The server counts two steps per repo: a fetch and a status. The page
polls the counter while its fetch request is open, fills the bar, and spins
the Reload glyph. The bar leaves once that request returns.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

PROGRESS = '{"active": true, "done": 3, "total": 10}'
BAR = """() => {
  const bar = document.getElementById('load-bar');
  const fill = bar.querySelector('i').getBoundingClientRect().width;
  return { hidden: bar.hidden, now: bar.getAttribute('aria-valuenow'),
    ratio: fill / bar.getBoundingClientRect().width,
    busy: document.getElementById('repos-refresh').getAttribute('aria-busy') };
}"""


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_the_bar_fills_from_the_counter_and_leaves_with_the_reply(
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
    # the fill animates to its width, so wait for ink and not the attribute
    page.wait_for_function(f"({BAR})().ratio > 0.29")
    bar = page.evaluate(BAR)
    assert bar["hidden"] is False
    assert bar["busy"] == "true", "the Reload glyph spins"
    assert 0.29 < bar["ratio"] < 0.31, bar
  finally:
    for r in held:
      r.continue_()
    page.unroute("**/api/fetch")
    page.unroute("**/api/progress")
  page.wait_for_function("document.getElementById('load-bar').hidden")
  bar = page.evaluate(BAR)
  assert bar["busy"] == "false"
  assert bar["now"] == "100", "the bar filled before it left"


def test_the_bar_belongs_to_the_dashboard(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto(1200)
  held: list[Any] = []
  page.route("**/api/fetch", lambda r: held.append(r))
  page.route(
    "**/api/progress",
    lambda r: r.fulfill(status=200, content_type="application/json", body=PROGRESS),
  )
  try:
    page.click("#repos-refresh")
    page.wait_for_function(f"({BAR})().ratio > 0.29")
    page.click(".repo-card:has-text('shop-web') .repo-name")
    assert page.evaluate(BAR)["hidden"] is True, "the repo view hides it at once"
    page.wait_for_timeout(900)
    assert page.evaluate(BAR)["hidden"] is True, "the counter does not bring it back"
    desktop.click("#back", 900)
    assert page.evaluate(BAR)["hidden"] is False, "the dashboard shows it again"
  finally:
    for r in held:
      r.continue_()
    page.unroute("**/api/fetch")
    page.unroute("**/api/progress")
  page.wait_for_function("document.getElementById('load-bar').hidden")
