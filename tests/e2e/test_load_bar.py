"""The header's loading bar marks the first repo list load.

The bar follows the nuu loading recipe, on the dashboard alone. It shows 200 ms
into the first list read and grows from the left on a transform. The dashboard
view is busy meanwhile. A fetch of the repo states spins the Reload glyph and
shows no bar.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.walk import Walker

pytestmark = [pytest.mark.e2e, pytest.mark.motion]

PROGRESS = '{"active": true, "done": 3, "total": 10}'
BAR = """() => {
  const bar = document.getElementById('load-bar');
  const style = getComputedStyle(bar);
  const matrix = new DOMMatrixReadOnly(style.transform);
  return { hidden: bar.hidden, role: bar.getAttribute('role'),
    motion: style.animationName, delay: style.animationDelay,
    origin: style.transformOrigin, scale: matrix.a, opacity: Number(style.opacity),
    region: document.getElementById('view-dashboard').getAttribute('aria-busy'),
    busy: document.getElementById('repos-refresh').getAttribute('aria-busy') };
}"""
BAR_HIDDEN = "document.getElementById('load-bar').hidden"
# jump the bar's own animation to `ms` from its start, delay included
FORWARD = """(ms) => {
  for (const a of document.getElementById('load-bar').getAnimations()) a.currentTime = ms;
}"""
DELAY_MS = 200
GROWTH_START = 0.05
GROWTH_END = 0.92
STILL_OPACITY = 0.45


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_the_bar_grows_from_the_left_while_the_first_list_loads(
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
    assert bar["role"] is None, "a decorative edge bar carries no progressbar role"
    assert bar["motion"] == "edge-loading"
    assert bar["delay"] == f"{DELAY_MS / 1000}s", "a fast read never flashes it"
    assert bar["origin"].startswith("0px"), "it grows from the left"
    assert bar["region"] == "true", "the dashboard view is busy"
    assert bar["busy"] != "true", "the Reload glyph stays still"
    assert page.is_visible("#repo-loading"), "the text line stays with the bar"
    page.evaluate(FORWARD, DELAY_MS + 800)
    late = page.evaluate(BAR)
    assert bar["scale"] <= late["scale"] <= GROWTH_END, (bar, late)
    assert late["scale"] > GROWTH_START, "the bar has grown"
    assert late["opacity"] > 0, "the bar shows once the delay is over"
  finally:
    for r in held:
      r.continue_()
    page.unroute("**/api/repos")
  page.wait_for_function(BAR_HIDDEN)
  page.wait_for_selector("#repo-loading", state="hidden")
  assert page.evaluate(BAR)["region"] == "false", "the view settles with the list"


def test_reduced_motion_holds_a_still_bar(desktop: Walker) -> None:
  page = desktop.page
  page.emulate_media(reduced_motion="reduce")
  held: list[Any] = []
  page.route("**/api/repos", lambda r: held.append(r))
  try:
    page.goto(desktop.url, wait_until="load")
    page.wait_for_function(f"!{BAR_HIDDEN}")
    bar = page.evaluate(BAR)
    assert bar["motion"] == "none"
    assert bar["scale"] == 1, "a full-width bar"
    assert bar["opacity"] == STILL_OPACITY
  finally:
    for r in held:
      r.continue_()
    page.unroute("**/api/repos")
    page.emulate_media(reduced_motion="no-preference")
  page.wait_for_function(BAR_HIDDEN)


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
  walker.goto()
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
    walker.frames()
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
