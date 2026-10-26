"""A live run keeps its stream, its button, and its log through everything around it.

The checks modal has its own job pane state. A dropped stream resumes where
it stopped. A run that keeps going says so when a cancel fails. A poll left
over from one repo never paints another.
"""

from __future__ import annotations

import pytest

from scripts.walk import Demo, Walker

pytestmark = pytest.mark.e2e

CARD = ".repo-card:has-text('{name}') .repo-name"
DRY = 'input[data-opt="dry_run"]'
ROWS = "#side-top .arena-item"
PARKED = "still running, waiting up to"
WAIT_MS = 30000


def set_dry(walker: Walker, on: bool) -> None:
  if walker.page.is_checked(DRY) != on:
    walker.click(DRY, 100)


def start_parked(walker: Walker, demo: Demo, name: str) -> None:
  """Open `name`, then start a run that waits on a check that never finishes."""
  walker.goto(1200)
  walker.click(CARD.format(name=name), 800)
  demo.slow_checks(True)
  set_dry(walker, False)
  walker.click("#start", 0)
  walker.page.wait_for_function(
    f"() => document.querySelector('#log').innerText.includes({PARKED!r})",
    timeout=WAIT_MS,
  )


def test_the_job_pane_leaves_the_live_run_alone(
  desktop: Walker, demo: Demo, signing: None
) -> None:
  page = desktop.page
  start_parked(desktop, demo, "billing-api")
  try:
    desktop.click(f"{ROWS} .arena-checks", 200)
    page.wait_for_selector("#modal[open]")
    desktop.click("#checks-list .check-row", 200)
    page.wait_for_selector("#checks-list li.open .job-pane")
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.querySelector('#modal').open")
    assert page.inner_text("#start").strip() == "Cancel"
    desktop.click("#start", 0)
    assert "cancelled" in desktop.wait_status("cancelled"), (
      "the button after the modal must cancel the run it still shows"
    )
  finally:
    demo.slow_checks(False)


def test_a_dropped_stream_resumes_without_repeating_lines(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto(1200)
  desktop.click(CARD.format(name="shop-web"), 800)
  page.route("**/api/jobs/*/events", lambda route: route.abort())
  try:
    set_dry(desktop, True)
    desktop.click("#start", 0)
    desktop.wait_status("exit")
    page.wait_for_timeout(300)
    rows = page.eval_on_selector_all("#log .log-row", "els => els.length")
    repos = page.request.get(f"{desktop.url}/api/repos").json()
    repo_id = next(r["id"] for r in repos if r["name"] == "shop-web")
    snap = page.request.get(f"{desktop.url}/api/repos/{repo_id}/jobs/latest").json()
    assert rows == len(snap["lines"]), (
      "each line once: the poll asks for the lines it lacks"
    )
  finally:
    page.unroute_all(behavior="ignoreErrors")


def test_a_poll_left_over_never_paints_another_repo(
  desktop: Walker, demo: Demo
) -> None:
  page = desktop.page
  desktop.goto(1200)
  desktop.click(CARD.format(name="billing-api"), 800)
  page.route("**/api/jobs/*/events", lambda route: route.abort())
  demo.slow_checks(True)
  try:
    set_dry(desktop, False)
    desktop.click("#start", 0)
    page.wait_for_function(
      f"() => document.querySelector('#log').innerText.includes({PARKED!r})",
      timeout=WAIT_MS,
    )
    # no e2e test runs infra-tools, so its view has no run of its own to show
    desktop.click("#back", 300)
    desktop.click(CARD.format(name="infra-tools"), 800)
    page.wait_for_timeout(2600)
    assert "billing-api" not in page.inner_text("#log"), "the old poll kept appending"
    status = desktop.status_text()
    demo.slow_checks(False)
    page.wait_for_timeout(4000)
    assert desktop.status_text() == status == "idle", (
      "the old run's end painted this view"
    )
  finally:
    demo.slow_checks(False)
    page.unroute_all(behavior="ignoreErrors")


def test_a_failed_cancel_never_says_cancelled(
  desktop: Walker, demo: Demo, signing: None
) -> None:
  page = desktop.page
  start_parked(desktop, demo, "docs-site")
  try:
    page.route("**/api/jobs/*/cancel", lambda route: route.abort())
    desktop.click("#start", 0)
    page.wait_for_selector("#toast.show")
    text = page.inner_text("#toast")
    assert text != "cancelled" and desktop.status_text() == "running", text
    page.unroute_all(behavior="ignoreErrors")
    desktop.click("#start", 0)
    assert "cancelled" in desktop.wait_status("cancelled")
  finally:
    demo.slow_checks(False)
    page.unroute_all(behavior="ignoreErrors")
