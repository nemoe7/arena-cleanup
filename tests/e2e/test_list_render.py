"""The dashboard list repaints only what changed, and every rollback reads the server.

A tick that changed nothing keeps focus, an armed Remove, and the open job
pane's scroll. A removal in flight stays out of a status refresh, and a
return from Settings reads the list again. A refused remove reloads the
list, and a refused clone reports under the field. The Reload glyph spins
until the last fetch ends.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

CARD = ".repo-card:has-text('{name}')"
ROWS = "#side-top .arena-item"
ONLINE = "() => window.dispatchEvent(new Event('online'))"
# a fetch of one path answers late, the page's own fetch does the rest
DELAY = """([tail, ms]) => {
  const orig = window.fetch;
  window.__fetch = orig;
  window.fetch = (u, i) => (typeof u === 'string' && u.endsWith(tail))
    ? new Promise((r) => setTimeout(() => r(orig(u, i)), ms))
    : orig(u, i);
}"""
RESTORE = "() => { if (window.__fetch) window.fetch = window.__fetch; }"


def fail(route: Any, message: str) -> None:
  route.fulfill(
    status=500, content_type="application/json", body=json.dumps({"error": message})
  )


def dirty(name: str):
  """A list read that says the clone of `name` has three changes."""

  def handle(route: Any) -> None:
    body = route.fetch().json()
    for repo in body:
      if repo["name"] == name:
        repo["status"]["dirty"] = 3
    route.fulfill(json=body)

  return handle


def test_a_removal_in_flight_stays_out_of_a_status_refresh(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto(1200)
  desktop.click(f"{CARD.format(name='data-pipeline')} .repo-name", 800)
  page.wait_for_selector(ROWS)
  assert desktop.count(ROWS) == 2
  page.route(
    "**/api/repos/*/arena/delete",
    lambda route: route.fulfill(status=200, content_type="application/json", body="{}"),
  )
  page.evaluate(DELAY, ["/arena/delete", 3000])
  try:
    desktop.click(f"{ROWS}:not(.selected) .arena-del", 300)
    desktop.click("#confirm-go", 300)
    assert desktop.count(ROWS) == 1, "the row leaves before the reply"
    desktop.click("#settings-btn", 300)
    desktop.click("#settings-back", 800)
    assert desktop.count(ROWS) == 1, "the status refresh brought the deleted row back"
    page.wait_for_timeout(3000)
  finally:
    page.evaluate(RESTORE)
    page.unroute_all(behavior="ignoreErrors")
