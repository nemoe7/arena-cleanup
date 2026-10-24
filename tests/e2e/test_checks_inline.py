"""A check row opens its Actions job in place: steps first, the paged log below.

The log opens on its last page and loads an older page when scrolled to its
top. A check from an app, not Actions, keeps its outbound link. The running
job test comes last, since its fake clock stays on the page.
"""

from __future__ import annotations

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

BILLING = ".repo-card:has-text('billing-api')"
SHOP = ".repo-card:has-text('shop-web')"
ROW = "#checks-list li:has-text('{name}') .check-row"
PANE = "#checks-list li.open .job-pane"
LOG = f"{PANE} .job-log"
PAGE = 400
TOTAL = 1000
STEPS = 6
POLL_MS = 10_000
LOG_STATE = """() => {
  const pre = document.querySelector('#checks-list li.open .job-log');
  const atBottom = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 1;
  return { atBottom, top: pre.scrollTop, scrollable: pre.scrollHeight > pre.clientHeight,
    first: pre.textContent.split('\\n')[0], last: pre.textContent.trimEnd().split('\\n').pop(),
    lines: document.querySelector('#checks-list li.open .job-lines').textContent };
}"""


def open_modal(walker: Walker, card: str) -> None:
  page = walker.page
  walker.goto(1200)
  page.wait_for_selector(f"{card} button.pill")
  page.click(f"{card} button.pill")
  page.wait_for_selector("#checks-modal[open]")


def close_modal(walker: Walker) -> None:
  walker.page.keyboard.press("Escape")
  walker.page.wait_for_function("!document.getElementById('checks-modal').open")


def test_a_failed_check_opens_its_steps_and_the_last_log_page(desktop: Walker) -> None:
  page = desktop.page
  open_modal(desktop, BILLING)
  try:
    assert desktop.count("#checks-modal.wide .modal-body") == 1, (
      "the modal scrolls inside"
    )
    page.click(ROW.format(name="test"))
    page.wait_for_selector(LOG)
    assert page.get_attribute(ROW.format(name="test"), "aria-expanded") == "true"
    assert desktop.count(f"{PANE} .job-steps li") == STEPS
    assert (
      desktop.text(f"{PANE} .job-steps li.failure .name")
      == "Run uv run --no-sync pytest"
    )
    assert desktop.text(f"{PANE} .job-steps li.failure .d") == "3 min 15 s"
    assert desktop.text(f"{PANE} .job-state").startswith("failure, ")
    assert page.get_attribute(f"{PANE} .job-head a", "href").endswith(
      "/runs/88/job/882"
    )
    log = page.evaluate(LOG_STATE)
    assert log["scrollable"] and log["atBottom"], "the log opens at its end"
    assert log["lines"] == f"lines {TOTAL - PAGE + 1} to {TOTAL} of {TOTAL}"
    assert log["last"].startswith("11:27:19 ##[error]"), "stamps shrink to the clock"
    assert log["first"].startswith("11:")
    assert desktop.count(f"{PANE} a[href]") == 1, "one GitHub link, no Open run button"
  finally:
    close_modal(desktop)


def test_scrolling_to_the_top_loads_an_older_page_and_keeps_the_place(
  desktop: Walker,
) -> None:
  page = desktop.page
  open_modal(desktop, BILLING)
  try:
    page.click(ROW.format(name="test"))
    page.wait_for_selector(LOG)
    for start in (TOTAL - 2 * PAGE + 1, 1):
      page.evaluate(
        "document.querySelector('#checks-list li.open .job-log').scrollTop = 0"
      )
      page.wait_for_function(
        f"document.querySelector('#checks-list li.open .job-lines').textContent.startsWith('lines {start} ')"
      )
      log = page.evaluate(LOG_STATE)
      assert log["top"] > 0, "the old first line stays in view after the prepend"
    assert page.evaluate(LOG_STATE)["lines"] == f"lines 1 to {TOTAL} of {TOTAL}"
  finally:
    close_modal(desktop)


SIZES = """() => {
  const li = document.querySelector('#checks-list li.open');
  const box = (sel) => li.querySelector(sel).getBoundingClientRect();
  const log = li.querySelector('.job-log');
  return { row: box('.check-row').height, name: box('.check-row .name').left,
    steps: box('.job-steps').left, button: box('.job-head .btn').height,
    pad: parseFloat(getComputedStyle(log).paddingLeft) };
}"""
CONTROL = 34
PHONE_CONTROL = 44
INSET = 12


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_the_pane_takes_the_house_sizes(
  request: pytest.FixtureRequest, width: str
) -> None:
  walker: Walker = request.getfixturevalue(width)
  page = walker.page
  open_modal(walker, BILLING)
  try:
    page.click(ROW.format(name="test"))
    page.wait_for_selector(LOG)
    sizes = page.evaluate(SIZES)
    assert sizes["row"] >= (PHONE_CONTROL if width == "phone" else 36), sizes
    assert sizes["button"] == (PHONE_CONTROL if width == "phone" else CONTROL), sizes
    assert abs(sizes["steps"] - sizes["name"]) < 1, (
      "the steps line up with the row name"
    )
    assert sizes["pad"] == INSET
  finally:
    close_modal(walker)


def test_an_app_check_keeps_its_outbound_link(desktop: Walker) -> None:
  open_modal(desktop, SHOP)
  try:
    row = "#checks-list li:has-text('e2e')"
    assert desktop.count(f"{row} .check-row") == 0
    assert desktop.text(f"{row} a.btn") == "Open run"
    assert desktop.count("#checks-list .check-row") == 3, (
      "the three Actions rows toggle"
    )
  finally:
    close_modal(desktop)


def test_a_running_job_shows_its_live_step_without_a_log_and_polls(
  desktop: Walker,
) -> None:
  page = desktop.page
  hits: list[str] = []
  page.on("request", lambda req: hits.append(req.url) if "/job?" in req.url else None)
  open_modal(desktop, BILLING)
  try:
    page.clock.install()
    page.click(ROW.format(name="build"))
    page.wait_for_selector(f"{PANE} .job-steps li.in_progress")
    assert desktop.text(f"{PANE} .job-steps li.in_progress .d") == "running"
    assert desktop.count(LOG) == 0
    assert desktop.text(f"{PANE} .job-note") == "The log arrives when the job ends."
    before = len(hits)
    with page.expect_request(lambda req: "/job?" in req.url, timeout=5000):
      page.clock.run_for(POLL_MS)
    assert len(hits) > before, "the steps refresh after the poll interval"
    page.click(ROW.format(name="build"))
    assert desktop.count_settled(PANE, 0) == 0, "the second click closes the pane"
  finally:
    close_modal(desktop)
