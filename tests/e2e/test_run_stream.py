"""A live run keeps its stream, its button, and its log through everything around it.

The checks modal has its own job pane state. A dropped stream resumes where
it stopped. A run that keeps going says so when a cancel fails. A poll left
over from one repo never paints another.

The poll test installs the Playwright clock. The clock keeps flowing with
real time, so the test after it sees no difference.
"""

from __future__ import annotations

import time

import pytest

from scripts.walk import Demo, Walker

pytestmark = pytest.mark.e2e

CARD = ".repo-card:has-text('{name}') .repo-name"
DRY = 'input[data-opt="dry_run"]'
ROWS = "#side-top .arena-item"
PARKED = "still running, waiting up to"
WAIT_MS = 30000
# the page polls a cut stream every 1200 ms
POLL_MS = 1300


def set_dry(walker: Walker, on: bool) -> None:
  if walker.page.is_checked(DRY) != on:
    walker.click(DRY)


def start_parked(walker: Walker, demo: Demo, name: str) -> None:
  """Open `name`, then start a run that waits on a check that never finishes."""
  walker.goto()
  walker.click(CARD.format(name=name))
  demo.slow_checks(True)
  set_dry(walker, False)
  walker.click("#start")
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
    desktop.click(f"{ROWS} .arena-checks")
    page.wait_for_selector("#modal[open]")
    desktop.click("#checks-list .check-row")
    page.wait_for_selector("#checks-list li.open .job-pane")
    page.keyboard.press("Escape")
    page.wait_for_function("() => !document.querySelector('#modal').open")
    assert page.inner_text("#start").strip() == "Cancel"
    desktop.click("#start")
    assert "cancelled" in desktop.wait_status("cancelled"), (
      "the button after the modal must cancel the run it still shows"
    )
  finally:
    demo.slow_checks(False)


def test_a_dropped_stream_resumes_without_repeating_lines(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto()
  desktop.click(CARD.format(name="shop-web"))
  page.route("**/api/jobs/*/events", lambda route: route.abort())
  try:
    set_dry(desktop, True)
    desktop.click("#start")
    desktop.wait_status("exit")
    repos = page.request.get(f"{desktop.url}/api/repos").json()
    repo_id = next(r["id"] for r in repos if r["name"] == "shop-web")
    snap = page.request.get(f"{desktop.url}/api/repos/{repo_id}/jobs/latest").json()
    # each line once: the poll asks for the lines it lacks
    page.wait_for_function(
      f"document.querySelectorAll('#log .log-row').length === {len(snap['lines'])}"
    )
  finally:
    page.unroute_all(behavior="ignoreErrors")


def poll_once(walker: Walker) -> None:
  """Run the page clock past one poll interval, so a poll left over fires now."""
  walker.page.clock.run_for(POLL_MS)
  walker.settle()


def wait_done(walker: Walker, name: str) -> None:
  """Wait until the latest run of `name` ended on the server."""
  repos = walker.page.request.get(f"{walker.url}/api/repos").json()
  rid = next(r["id"] for r in repos if r["name"] == name)
  deadline = time.monotonic() + WAIT_MS / 1000
  while time.monotonic() < deadline:
    snap = walker.page.request.get(f"{walker.url}/api/repos/{rid}/jobs/latest").json()
    if snap.get("status") == "done":
      return
    time.sleep(0.2)
  raise AssertionError("the parked run never ended")


def test_a_poll_left_over_never_paints_another_repo(
  desktop: Walker, demo: Demo, signing: None
) -> None:
  page = desktop.page
  desktop.goto()
  desktop.click(CARD.format(name="billing-api"))
  page.route("**/api/jobs/*/events", lambda route: route.abort())
  demo.slow_checks(True)
  try:
    set_dry(desktop, False)
    # the stream is cut, so the run's view polls on page timers: the fake clock drives them
    page.clock.install()
    desktop.click("#start")
    page.wait_for_function(
      f"() => document.querySelector('#log').innerText.includes({PARKED!r})",
      timeout=WAIT_MS,
    )
    # no e2e test runs infra-tools, so its view has no run of its own to show
    desktop.click("#back")
    desktop.click(CARD.format(name="infra-tools"))
    poll_once(desktop)
    assert "billing-api" not in page.inner_text("#log"), "the old poll kept appending"
    status = desktop.status_text()
    demo.slow_checks(False)
    wait_done(desktop, "billing-api")
    poll_once(desktop)
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
    desktop.click("#start")
    page.wait_for_selector("#toast.show")
    text = page.inner_text("#toast")
    assert text != "cancelled" and desktop.status_text() == "running", text
    page.unroute_all(behavior="ignoreErrors")
    desktop.click("#start")
    assert "cancelled" in desktop.wait_status("cancelled")
  finally:
    demo.slow_checks(False)
    page.unroute_all(behavior="ignoreErrors")
