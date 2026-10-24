"""The phase rows measure one contiguous timeline.

A line names the current phase or a later one, never an earlier one. The
next phase starts where the last one ends. So the rows add up to the wall
clock of the run.
"""

from __future__ import annotations

import json

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

# a run's lines in engine order. A stale branch at the start and the
# commit scan after the PR gate once moved the clock back.
RUN = [
  ("INFO", "arena-cleanup 0.3.1 starting"),
  ("INFO", "claimed emails=nemo@example.com; claimed names=nemo"),
  ("OK", "fetched and pruned origin"),
  ("INFO", "scanning local arena/* branches"),
  ("WARN", "deleting stale local branch arena/old"),
  ("INFO", "switching to arena/session-4 (tracking origin/arena/session-4)"),
  ("INFO", "checking PR status for arena/session-4"),
  ("OK", 'check "lint": SUCCESS'),
  ("OK", "PR #57 checks ok"),
  ("INFO", "scanning 23 commit(s) as Nemo <nemo@example.com>"),
  (
    "OK",
    "history rewritten: 23 commit(s): 20 rewritten, 20 signed, 3 untouched (4.2s)",
  ),
  ("INFO", "pushing (with lease) HEAD -> refs/heads/main"),
  ("OK", "pushed 2222222 to origin/main"),
  ("INFO", "returning to main"),
  ("OK", "deleted origin/arena/session-4"),
  ("OK", "done: 23 commits rewritten"),
]
TIMES = {
  "prepare": "6.0s",
  "pr": "3.0s",
  "rewrite": "2.0s",
  "publish": "2.0s",
  "sync": "2.0s",
}


def rows_after(walker: Walker, lines: list[tuple[str, str]]) -> dict[str, str]:
  """The row times after the page reattaches to a finished run of `lines`."""
  snap = {
    "id": "fake",
    "status": "done",
    "exit": 0,
    "cancelled": False,
    "elapsed": float(len(lines) - 1),
    "lines": [
      {"t": 1_700_000_000 + i, "text": f"2026-10-24T10:00:{i:02d}+0000 {level} {text}"}
      for i, (level, text) in enumerate(lines)
    ],
  }
  pattern = "**/api/repos/*/jobs/latest"
  walker.page.route(
    pattern,
    lambda route: route.fulfill(
      status=200, content_type="application/json", body=json.dumps(snap)
    ),
  )
  try:
    walker.goto(1200)
    walker.click(".repo-card:has-text('infra-tools') .repo-name", 800)
    pairs = walker.page.eval_on_selector_all(
      ".phase",
      "els => els.map((e) => [e.dataset.phase, e.querySelector('.phase-time').textContent])",
    )
    return dict(pairs)
  finally:
    walker.page.unroute(pattern)


def test_the_rows_add_up_to_the_wall_clock(desktop: Walker) -> None:
  rows = rows_after(desktop, RUN)
  assert rows == TIMES, "each phase runs until the next one starts"
  assert sum(float(v[:-1]) for v in rows.values()) == float(len(RUN) - 1)


def test_an_early_deletion_and_a_late_scan_stay_in_their_phases(
  desktop: Walker,
) -> None:
  rows = rows_after(desktop, RUN[:10])
  assert rows["prepare"] == "6.0s", "the stale branch deletion stays in Prepare"
  assert rows["pr"] == "3.0s", (
    "the commit scan opens the rewrite, it does not stretch Prepare"
  )
  assert rows["rewrite"] == "<0.1s"
  assert rows["sync"] == "", "Clean up does not start before the push"
