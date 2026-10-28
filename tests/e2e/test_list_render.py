"""The dashboard list repaints only what changed, and every rollback reads the server.

A tick that changed nothing keeps focus, an armed Remove, and the open job
pane's scroll. A removal in flight stays out of a status refresh, and a
return from Settings reads the list again. A refused remove reloads the
list, and a refused clone reports under the field. An error toast stays to
be read, and the Reload glyph spins until the last fetch ends.

Two tests install the Playwright clock, so their page timers run out at
once. The clock keeps flowing with real time, so the later tests see no
difference.
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
# a changed list rebuilds every card, so the old node leaves the document
REBUILT = "e => !e.isConnected"
# the test holds the delete answer this long
DELETE_MS = 3000
# the page disarms an armed Remove after this long
DISARM_MS = 4000
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


def tick(walker: Walker) -> None:
  """Fire the online event, and return once the page painted the list it read."""
  page = walker.page
  with page.expect_event("requestfinished", lambda r: r.url.endswith("/api/repos")):
    page.evaluate(ONLINE)
  walker.frames()


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
  desktop.goto()
  desktop.click(f"{CARD.format(name='data-pipeline')} .repo-name")
  page.wait_for_selector(ROWS)
  assert desktop.count(ROWS) == 2
  page.route(
    "**/api/repos/*/arena/delete",
    lambda route: route.fulfill(status=200, content_type="application/json", body="{}"),
  )
  page.clock.install()
  page.evaluate(DELAY, ["/arena/delete", DELETE_MS])
  try:
    desktop.click(f"{ROWS}:not(.selected) .arena-del")
    desktop.click("#confirm-go")
    assert desktop.count_settled(ROWS, 1) == 1, "the row leaves before the reply"
    desktop.click("#settings-btn")
    desktop.click("#settings-back")
    assert desktop.count(ROWS) == 1, "the status refresh brought the deleted row back"
    # the held delete lands before the next test starts
    with page.expect_response("**/arena/delete"):
      page.clock.run_for(DELETE_MS)
  finally:
    page.evaluate(RESTORE)
    page.unroute_all(behavior="ignoreErrors")


def test_a_tick_that_changed_nothing_keeps_focus_and_an_armed_remove(
  desktop: Walker,
) -> None:
  page = desktop.page
  desktop.goto()
  page.clock.install()
  rm = f"{CARD.format(name='billing-api')} .rm"
  desktop.click(rm)
  assert page.eval_on_selector(
    rm, "e => e.classList.contains('armed') && e === document.activeElement"
  )
  tick(desktop)
  assert page.eval_on_selector(rm, "e => e.classList.contains('armed')"), (
    "the tick disarmed Remove"
  )
  assert page.eval_on_selector(rm, "e => e === document.activeElement"), (
    "the tick dropped focus"
  )
  page.keyboard.press("Escape")
  page.clock.run_for(DISARM_MS)


def test_a_changed_list_keeps_the_focus_on_the_same_control(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto()
  name = f"{CARD.format(name='docs-site')} .repo-name"
  page.focus(name)
  page.route(lambda url: url.endswith("/api/repos"), dirty("docs-site"))
  try:
    old = page.query_selector(name)
    page.evaluate(ONLINE)
    page.wait_for_function(REBUILT, arg=old)
    assert page.eval_on_selector(name, "e => e === document.activeElement"), (
      "focus fell off the card"
    )
  finally:
    page.unroute_all(behavior="ignoreErrors")


def test_a_changed_list_keeps_the_job_log_scroll(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto()
  desktop.click(f"{CARD.format(name='billing-api')} button.pill")
  page.wait_for_selector("#modal[open]")
  desktop.click("#checks-list li:has-text('test') .check-row")
  pre = "#checks-list li.open .job-log"
  page.wait_for_selector(pre)
  page.eval_on_selector(pre, "e => { e.scrollTop = Math.floor(e.scrollHeight / 2); }")
  before = page.eval_on_selector(pre, "e => e.scrollTop")
  assert before > 0
  page.route(lambda url: url.endswith("/api/repos"), dirty("billing-api"))
  try:
    old = page.query_selector(CARD.format(name="billing-api"))
    page.evaluate(ONLINE)
    page.wait_for_function(REBUILT, arg=old)
    assert abs(page.eval_on_selector(pre, "e => e.scrollTop") - before) <= 2, (
      "the render moved the log"
    )
  finally:
    page.unroute_all(behavior="ignoreErrors")
    page.keyboard.press("Escape")


def test_a_return_from_settings_reads_the_list_again(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto()
  desktop.click("#settings-btn")
  with page.expect_request(lambda r: r.url.endswith("/api/repos")):
    desktop.click("#settings-back")


def test_a_refused_remove_reloads_the_list(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto()
  cards = desktop.count(".repo-card")
  page.route("**/api/repos/*/remove", lambda route: fail(route, "origin refused"))
  try:
    with page.expect_request(
      lambda r: r.url.endswith("/api/repos") and r.method == "GET"
    ):
      rm = f"{CARD.format(name='infra-tools')} .rm"
      desktop.click(rm)
      desktop.click(rm)
    assert "origin refused" in desktop.text("#toast")
    assert desktop.count_settled(".repo-card", cards) == cards
  finally:
    page.unroute_all(behavior="ignoreErrors")


def test_a_refused_clone_reports_under_the_field(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto()
  page.route(
    "**/api/repos",
    lambda route: (
      fail(route, "clone refused")
      if route.request.method == "POST"
      else route.continue_()
    ),
  )
  try:
    page.fill("#add-source", "https://github.com/acme/refused.git")
    desktop.click("#add-btn")
    assert page.is_visible("#add-error")
    assert desktop.text("#add-error") == "clone refused"
    assert page.get_attribute("#add-source", "aria-invalid") == "true"
    assert page.eval_on_selector("#toast", "e => e.classList.contains('show')") is False
    assert desktop.count(".repo-card.pending") == 0
  finally:
    page.unroute_all(behavior="ignoreErrors")
    page.fill("#add-source", "")


def test_an_error_toast_stays_to_be_read(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto()
  page.route("**/api/repos/*/remove", lambda route: fail(route, "origin refused"))
  try:
    rm = f"{CARD.format(name='docs-site')} .rm"
    desktop.click(rm)
    desktop.click(rm)
    assert page.eval_on_selector("#toast", "e => e.classList.contains('show')"), (
      "the error toast went at the receipt's 2.2 s"
    )
  finally:
    page.unroute_all(behavior="ignoreErrors")


def test_the_reload_glyph_spins_until_the_last_fetch_ends(desktop: Walker) -> None:
  page = desktop.page
  busy = "() => document.getElementById('repos-refresh').getAttribute('aria-busy')"
  # the route holds each fetch until the test lets it through
  held: list[Any] = []
  page.route("**/api/fetch", lambda route: held.append(route))
  try:
    desktop.goto()
    page.click("#repos-refresh")
    desktop.until(lambda: len(held) >= 2, "the Reload click sent its fetch")
    assert len(held) == 2, "the page-load fetch and the Reload click are both in flight"
    assert page.evaluate(busy) == "true"
    with page.expect_event("requestfinished", lambda r: r.url.endswith("/api/fetch")):
      held[0].continue_()
    desktop.frames()
    assert page.evaluate(busy) == "true", (
      "the first fetch's end stopped the glyph early"
    )
    held[1].continue_()
    page.wait_for_function(f"{busy} === 'false'", timeout=5000)
  finally:
    page.unroute_all(behavior="ignoreErrors")
