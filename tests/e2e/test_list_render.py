"""The dashboard list repaints only what changed, and every rollback reads the server.

A tick that changed nothing keeps focus, an armed Remove, and the open job
pane's scroll. A removal in flight stays out of a status refresh, and a
return from Settings reads the list again. A refused remove reloads the
list, and a refused clone reports under the field. An error toast stays to
be read, and the Reload glyph spins until the last fetch ends.
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


def test_a_tick_that_changed_nothing_keeps_focus_and_an_armed_remove(
  desktop: Walker,
) -> None:
  page = desktop.page
  desktop.goto(1200)
  rm = f"{CARD.format(name='billing-api')} .rm"
  desktop.click(rm, 100)
  assert page.eval_on_selector(
    rm, "e => e.classList.contains('armed') && e === document.activeElement"
  )
  page.evaluate(ONLINE)
  page.wait_for_timeout(800)
  assert page.eval_on_selector(rm, "e => e.classList.contains('armed')"), (
    "the tick disarmed Remove"
  )
  assert page.eval_on_selector(rm, "e => e === document.activeElement"), (
    "the tick dropped focus"
  )
  page.keyboard.press("Escape")
  page.wait_for_timeout(4200)


def test_a_changed_list_keeps_the_focus_on_the_same_control(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto(1200)
  name = f"{CARD.format(name='docs-site')} .repo-name"
  page.focus(name)
  page.route(lambda url: url.endswith("/api/repos"), dirty("docs-site"))
  try:
    page.evaluate(ONLINE)
    page.wait_for_timeout(800)
    assert page.eval_on_selector(name, "e => e === document.activeElement"), (
      "focus fell off the card"
    )
  finally:
    page.unroute_all(behavior="ignoreErrors")


def test_a_changed_list_keeps_the_job_log_scroll(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto(1200)
  desktop.click(f"{CARD.format(name='billing-api')} button.pill", 300)
  page.wait_for_selector("#checks-modal[open]")
  desktop.click("#checks-list li:has-text('test') .check-row", 300)
  pre = "#checks-list li.open .job-log"
  page.wait_for_selector(pre)
  page.eval_on_selector(pre, "e => { e.scrollTop = Math.floor(e.scrollHeight / 2); }")
  before = page.eval_on_selector(pre, "e => e.scrollTop")
  assert before > 0
  page.route(lambda url: url.endswith("/api/repos"), dirty("billing-api"))
  try:
    page.evaluate(ONLINE)
    page.wait_for_timeout(800)
    assert abs(page.eval_on_selector(pre, "e => e.scrollTop") - before) <= 2, (
      "the render moved the log"
    )
  finally:
    page.unroute_all(behavior="ignoreErrors")
    page.keyboard.press("Escape")


def test_a_return_from_settings_reads_the_list_again(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto(1200)
  desktop.click("#settings-btn", 400)
  with page.expect_request(lambda r: r.url.endswith("/api/repos")):
    desktop.click("#settings-back", 0)


def test_a_refused_remove_reloads_the_list(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto(1200)
  cards = desktop.count(".repo-card")
  page.route("**/api/repos/*/remove", lambda route: fail(route, "origin refused"))
  try:
    with page.expect_request(
      lambda r: r.url.endswith("/api/repos") and r.method == "GET"
    ):
      rm = f"{CARD.format(name='infra-tools')} .rm"
      desktop.click(rm, 100)
      desktop.click(rm, 300)
    assert "origin refused" in desktop.text("#toast")
    assert desktop.count_settled(".repo-card", cards) == cards
  finally:
    page.unroute_all(behavior="ignoreErrors")


def test_a_refused_clone_reports_under_the_field(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto(1200)
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
    desktop.click("#add-btn", 600)
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
  desktop.goto(1200)
  page.route("**/api/repos/*/remove", lambda route: fail(route, "origin refused"))
  try:
    rm = f"{CARD.format(name='docs-site')} .rm"
    desktop.click(rm, 100)
    desktop.click(rm, 3000)
    assert page.eval_on_selector("#toast", "e => e.classList.contains('show')"), (
      "the error toast went at the receipt's 2.2 s"
    )
  finally:
    page.unroute_all(behavior="ignoreErrors")
