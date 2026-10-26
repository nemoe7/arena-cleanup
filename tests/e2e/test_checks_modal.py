"""A PR checks pill opens a modal with the checks of that PR.

The pill is a button when the PR has checks. The modal lists one row per
check with its state glyph and carries the PR link. An Actions check row is a
toggle for its job.

A repo view opens this modal from its arena row. Escape closes it.
"""

from __future__ import annotations

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

CARD = ".repo-card:has-text('billing-api')"
MODAL = """() => {
  const dlg = document.getElementById('modal');
  return { open: dlg.open, title: document.getElementById('modal-title').textContent,
    rows: [...dlg.querySelectorAll('.check-list li')]
      .map((li) => [li.className, li.querySelector('.name').textContent,
        li.querySelector('.check-row') ? 'job' : li.querySelector('a') ? 'link' : 'none']),
    pr: dlg.open ? document.getElementById('checks-pr').getAttribute('href') : null };
}"""
ROWS = [
  ["passed", "CI / lint", "job"],
  ["failed", "CI / test", "job"],
  ["running", "CI / build", "job"],
]


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_the_pill_opens_the_checks_and_the_repo_view_shares_the_modal(
  request: pytest.FixtureRequest, width: str
) -> None:
  walker: Walker = request.getfixturevalue(width)
  page = walker.page
  walker.goto(1200)
  page.wait_for_selector(f"{CARD} button.pill")
  assert page.evaluate(MODAL)["open"] is False
  assert page.get_attribute(f"{CARD} button.pill", "title") == "Show PR checks"
  page.click(f"{CARD} button.pill")
  page.wait_for_selector("#modal[open]")
  modal = page.evaluate(MODAL)
  assert modal["title"] == "PR #88 checks"
  assert modal["rows"] == ROWS, "one row per check, glyph by result, a job toggle"
  assert modal["pr"].endswith("/pull/88")
  page.keyboard.press("Escape")
  page.wait_for_function("!document.getElementById('modal').open")
  walker.click(f"{CARD} .repo-name", 800)
  page.wait_for_selector(".arena-checks")
  assert page.get_attribute(".arena-checks", "title") == "Show PR checks"
  assert (
    page.get_attribute(".arena-checks", "aria-label")
    == "Show PR checks of arena/1b9d4c7e-billing-api"
  )
  page.click(".arena-checks")
  page.wait_for_selector("#modal[open]")
  assert page.evaluate(MODAL)["rows"] == ROWS
  page.keyboard.press("Escape")
  page.wait_for_function("!document.getElementById('modal').open")
  walker.click("#back", 600)


def test_a_row_without_a_pr_keeps_its_plain_pill(desktop: Walker) -> None:
  desktop.goto(1200)
  row = ".repo-card:has-text('data-pipeline') .arena-row:has-text('6d8b3a4e')"
  desktop.page.wait_for_selector(row)
  assert desktop.count(f"{row} span.pill:not(.ahead)") == 1
  assert desktop.count(f"{row} button.pill, {row} .prlink") == 0
