"""A commit row reads like the GitHub app's: subject, check state, age, then the author.

The hash and the full stamp show once a tap expands the row (docs/design.md).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

ROW = "#commits .commit"
# the rows' ages, newest first, and the check state of each
AGES = [(32, "m"), (1, "h"), (10, "h"), (3, "d")]
STATES = ["success", "failure", "pending", None]
LONG = "fix(ui): a subject long enough to run past the right edge of the commit list on every width"
ROWS_JS = """() => [...document.querySelectorAll('#commits .commit')].map((row) => ({
  lines: Math.round(row.querySelector('.subject').getBoundingClientRect().height
    / parseFloat(getComputedStyle(row.querySelector('.subject')).lineHeight)),
  cut: row.querySelector('.subject').scrollWidth > row.querySelector('.subject').clientWidth,
  ci: row.querySelector('.ci')?.className.replace('ci ', '') ?? null,
  glyph: row.querySelector('.ci .dot') ? 'dot' : row.querySelector('.ci .ico-svg') ? 'ico-svg' : null,
  age: row.querySelector('.age').textContent,
  stamp: row.querySelector('.age').title,
  meta: [...row.querySelector('.meta').children].map((e) => e.className.split(' ')[0]),
  authored: row.querySelector('.meta .did').textContent,
  sig: row.querySelector('.meta .sig svg') !== null,
  unsigned: row.querySelector('.meta .sig').classList.contains('none'),
  more: getComputedStyle(row.querySelector('.more')).display,
  hash: row.querySelector('.more .sha').textContent,
  sha: row.querySelector('.more .sha') !== null,
  rightEdge: row.querySelector('.age').getBoundingClientRect().right
    <= row.getBoundingClientRect().right,
}))"""


def page_body(now: datetime) -> dict[str, Any]:
  commits = []
  for n, ((count, unit), state) in enumerate(zip(AGES, STATES, strict=True)):
    back = {"m": "minutes", "h": "hours", "d": "days"}[unit]
    commits.append(
      {
        "sha": f"{n:x}" * 40,
        "short": f"{n:x}" * 7,
        "subject": LONG if n == 0 else f"commit {n}",
        "author": "demo",
        "date": (now - timedelta(**{back: count}) - timedelta(seconds=20)).isoformat(),
        "signed": n != 1,
        "avatar": None,
        "ci": state,
      }
    )
  return {"branch": "main", "total": 4, "shown": 4, "next": None, "commits": commits}


def open_rows(walker: Walker) -> list[dict[str, Any]]:
  page = walker.page
  body = json.dumps(page_body(datetime.now(UTC)))
  page.route(
    "**/api/repos/*/commits?*",
    lambda route: route.fulfill(status=200, content_type="application/json", body=body),
  )
  walker.goto()
  walker.click(".repo-card:has-text('shop-web') .repo-name")
  page.wait_for_function(f"document.querySelectorAll('{ROW}').length === 4")
  return page.evaluate(ROWS_JS)


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_a_row_reads_subject_state_age_then_author(
  request: pytest.FixtureRequest, width: str
) -> None:
  walker: Walker = request.getfixturevalue(width)
  rows = open_rows(walker)
  assert [r["age"] for r in rows] == [f"{n}{u}" for n, u in AGES]
  assert [r["ci"] for r in rows] == STATES
  assert rows[0]["glyph"] == "ico-svg" and rows[1]["glyph"] == "ico-svg"
  assert rows[2]["glyph"] == "dot", "a running check pulses"
  assert all(r["lines"] == 1 for r in rows), "one line per subject"
  assert rows[0]["cut"] and not rows[1]["cut"], "the long subject ends in an ellipsis"
  assert all(r["rightEdge"] for r in rows), "the age sits at the right edge"
  assert all(r["meta"] == ["avatar", "author", "did", "sig"] for r in rows)
  assert all(r["authored"] == "authored" for r in rows)
  assert all(r["sig"] for r in rows), (
    "a signed and an unsigned commit both draw a glyph"
  )
  assert [r["unsigned"] for r in rows] == [False, True, False, False]
  assert all(r["more"] == "none" for r in rows), "the hash waits for a tap"
  assert all(r["stamp"] for r in rows), "the full stamp rides on the age"


def test_a_tap_opens_the_hash_and_the_full_stamp_in_the_row(desktop: Walker) -> None:
  page = desktop.page
  open_rows(desktop)
  first = f"{ROW}:first-child"
  desktop.click(first)
  rows = page.evaluate(ROWS_JS)
  assert page.get_attribute(first, "aria-expanded") == "true"
  assert rows[0]["more"] == "flex" and rows[0]["hash"] == "0" * 7
  assert rows[0]["lines"] > 1 and not rows[0]["cut"], "the whole subject wraps"
  assert rows[1]["more"] == "none", "the other rows stay folded"
  assert desktop.text(f"{first} .more .stamp") == rows[0]["stamp"]
  assert desktop.visible("#view-repo"), "no page change: the row alone opened"
  desktop.click(first)
  assert page.get_attribute(first, "aria-expanded") == "false"
