"""A check row opens its Actions job in place: its steps, each a toggle for its log.

The first failed step opens on its last page and loads an older page when
scrolled to its top. A passed job opens no step. A check from an app, not
Actions, keeps its outbound link. The running job test comes last, since its
fake clock stays on the page.
"""

from __future__ import annotations

import re

import pytest

from tests.e2e.harness import Walker

pytestmark = pytest.mark.e2e

BILLING = ".repo-card:has-text('billing-api')"
SHOP = ".repo-card:has-text('shop-web')"
ROW = "#checks-list li:has-text('{name}') .check-row"
PANE = "#checks-list li.open .job-pane"
STEP = f"{PANE} .job-steps li:has-text('{{name}}')"
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


def counts(walker: Walker, selector: str) -> list[int]:
  """The numbers in an element's text, as `lines 1 to 400 of 1000` carries three."""
  return [int(n) for n in re.findall(r"\d+", walker.text(selector))]


def open_modal(walker: Walker, card: str) -> None:
  page = walker.page
  walker.goto()
  page.wait_for_selector(f"{card} button.pill")
  page.click(f"{card} button.pill")
  page.wait_for_selector("#modal[open]")


def close_modal(walker: Walker) -> None:
  walker.page.keyboard.press("Escape")
  walker.page.wait_for_function("!document.getElementById('modal').open")


def test_a_failed_check_opens_its_steps_and_the_last_log_page(desktop: Walker) -> None:
  page = desktop.page
  open_modal(desktop, BILLING)
  try:
    assert desktop.count("#modal.wide .modal-body") == 1, "the modal scrolls inside"
    page.click(ROW.format(name="test"))
    page.wait_for_selector(LOG)
    assert page.get_attribute(ROW.format(name="test"), "aria-expanded") == "true"
    assert desktop.count(f"{PANE} .job-steps li") == STEPS
    assert "pytest" in desktop.text(f"{PANE} .job-steps li.failure .name")
    assert desktop.text(f"{PANE} .job-steps li.failure .d") == "3 min 15 s"
    assert desktop.count(f"{PANE} .job-steps li.open") == 1, "the failed step opens"
    assert page.get_attribute(f"{PANE} li.failure .step", "aria-expanded") == "true"
    assert desktop.count(f"{PANE} li.failure .job-log") == 1, "its log sits in its row"
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


def test_a_reopened_check_paints_from_its_kept_detail(desktop: Walker) -> None:
  page = desktop.page
  hits: list[str] = []
  page.on("request", lambda req: hits.append(req.url) if "/job?" in req.url else None)
  open_modal(desktop, BILLING)
  try:
    row = ROW.format(name="test")
    page.click(row)
    page.wait_for_selector(LOG)
    page.click(row)
    page.wait_for_selector(PANE, state="detached")
    page.click(row)
    page.wait_for_selector(LOG)
    log = page.evaluate(LOG_STATE)
    assert log["lines"] == f"lines {TOTAL - PAGE + 1} to {TOTAL} of {TOTAL}"
    assert log["atBottom"], "the kept log opens at its end again"
    assert desktop.count(f"{PANE} .job-steps li") == STEPS
    assert len(hits) == 1, hits
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


def test_a_step_row_opens_only_its_own_lines(desktop: Walker) -> None:
  page = desktop.page
  open_modal(desktop, BILLING)
  try:
    page.click(ROW.format(name="test"))
    page.wait_for_selector(LOG)
    post = STEP.format(name="Post Checkout")
    page.click(f"{post} .step")
    page.wait_for_selector(f"{post} .job-log")
    lines = desktop.text(f"{post} .job-log").split("\n")
    assert len(lines) == 1 and "cleanup" in lines[0], (
      "a step in the second the step before ended keeps only its own line"
    )
    assert "[error]" not in lines[0], "the error line stays with the failed step"
    assert counts(desktop, f"{post} .job-lines") == [1, 1, 1]
    assert desktop.count(LOG) == 2, "the failed step stays open"
    assert counts(desktop, f"{PANE} li.failure .job-lines") == [
      TOTAL - PAGE + 1,
      TOTAL,
      TOTAL,
    ], "and it keeps its line count"
    setup = STEP.format(name="Set up job")
    page.click(f"{setup} .step")
    page.wait_for_selector(f"{setup} .job-log")
    first = desktop.text(f"{setup} .job-log").split("\n")
    assert len(first) == 2 and first[0].startswith("11:21:00 "), first
    page.click(f"{post} .step")
    assert desktop.count_settled(f"{post} .job-log", 0) == 0, "a second click closes"
    assert page.get_attribute(f"{post} .step", "aria-expanded") == "false"
    assert desktop.count(LOG) == 2
  finally:
    close_modal(desktop)


def test_a_passed_job_opens_no_step(desktop: Walker) -> None:
  page = desktop.page
  open_modal(desktop, BILLING)
  try:
    page.click(ROW.format(name="lint"))
    page.wait_for_selector(f"{PANE} .job-steps li.success")
    assert desktop.count(f"{PANE} .job-steps li") == STEPS
    assert desktop.count_settled(LOG, 0) == 0, "no step opens on a passed job"
    assert desktop.count(f"{PANE} .job-steps li.open") == 0
    assert desktop.count(f"{PANE} .job-note:not([hidden])") == 0, "and no note"
  finally:
    close_modal(desktop)


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
    assert desktop.text(f"{PANE} .job-note"), "a note stands in for the log"
    before = len(hits)
    with page.expect_request(lambda req: "/job?" in req.url, timeout=5000):
      page.clock.run_for(POLL_MS)
    assert len(hits) > before, "the steps refresh after the poll interval"
    page.click(ROW.format(name="build"))
    assert desktop.count_settled(PANE, 0) == 0, "the second click closes the pane"
  finally:
    close_modal(desktop)
