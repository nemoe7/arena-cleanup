"""A check row reads like GitHub's PR checks list.

The name is `Workflow / Job`, the glyph carries the state, and a phrase names
the state with its run time. GitHub's rollup carries no event, so a row shows
none. An app check has no workflow and keeps its outbound link.
"""

from __future__ import annotations

import pytest

from tests.e2e.harness import Walker
from tests.e2e.test_checks_inline import BILLING, SHOP, close_modal, open_modal

pytestmark = pytest.mark.e2e

ROWS = "#checks-list li"
TEXTS = """(sel) => [...document.querySelectorAll(sel)].map((li) => ({
  name: li.querySelector('.name').textContent,
  phrase: li.querySelector('.phrase').textContent,
  title: (li.querySelector('.check-row') || li.querySelector('.name')).title,
  phraseRight: li.querySelector('.phrase').getBoundingClientRect().right,
  tailLeft: (li.querySelector('.chev') || li.querySelector('a.btn')).getBoundingClientRect().left,
  marks: li.querySelectorAll('svg').length,
}))"""


def test_a_row_names_the_workflow_and_job_and_phrases_its_state(
  desktop: Walker,
) -> None:
  open_modal(desktop, BILLING)
  try:
    rows = desktop.page.evaluate(TEXTS, ROWS)
    assert [r["name"] for r in rows] == ["CI / lint", "CI / test", "CI / build"]
    assert [r["phrase"] for r in rows] == [
      "Successful in 1 min 11 s",
      "Failed in 1 min 59 s",
      "In progress",
    ]
    assert rows[1]["title"] == "CI / test: failed in 1 min 59 s"
    assert all(r["phraseRight"] <= r["tailLeft"] for r in rows), (
      "the phrase sits before the chevron"
    )
    assert [r["marks"] for r in rows] == [2, 2, 1], (
      "state glyph and chevron, no GitHub mark; the running row holds a dot"
    )
  finally:
    close_modal(desktop)


def test_an_app_check_has_no_workflow_and_keeps_its_phrase(desktop: Walker) -> None:
  open_modal(desktop, SHOP)
  try:
    rows = desktop.page.evaluate(TEXTS, ROWS)
    e2e = next(r for r in rows if r["name"] == "e2e")
    assert e2e["phrase"] == "Successful in 3 min 35 s"
    assert e2e["phraseRight"] <= e2e["tailLeft"], "the phrase sits before Open run"
  finally:
    close_modal(desktop)
