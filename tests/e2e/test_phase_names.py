# nonemo: STE902
"""A branch or repo name with phase words does not move the run.

The phase tests read the start of each engine line. The branch here is
arena/cleanup-done, and the backup sits under a done-work folder. PR checks,
Rewrite and sign, and Push stay in place, so every row reads done at the end.
"""

from __future__ import annotations

import pytest

from scripts.walk import Walker
from tests.e2e.test_phase_modals import open_run

pytestmark = pytest.mark.e2e

BRANCH = "arena/cleanup-done"
RUN = [
  ("INFO", "arena-cleanup 0.3.8 starting"),
  ("INFO", "claimed emails=bot@example.com; claimed names=bot; sign=yes"),
  ("OK", "fetched and pruned origin"),
  ("INFO", "default branch: main"),
  ("INFO", "current branch: main"),
  ("INFO", "on main, locating origin/arena/* branch"),
  ("INFO", f"switching to {BRANCH} (tracking origin/{BRANCH})"),
  ("OK", "already up to date (de96315)"),
  ("INFO", "creating backup bundle"),
  ("OK", "backup written to /srv/done-work/push-tags/.git/cleanup-done.bundle"),
  ("INFO", "scanning 5 commit(s) as Nemo <nemo@example.com>"),
  ("OK", "history rewritten: 5 commit(s): 5 rewritten, 5 signed, 0 untouched (1.2s)"),
  ("INFO", f"checking PR status for {BRANCH}"),
  ("INFO", "found PR #57"),
  ("OK", 'check "lint": SUCCESS'),
  ("OK", 'check "deleted-files-done": SUCCESS'),
  ("OK", "PR #57 checks ok"),
  ("INFO", "pushing (with lease) HEAD -> refs/heads/main"),
  ("OK", "pushed 2222222 to origin/main"),
  ("INFO", "returning to main"),
  ("OK", f"deleted origin/{BRANCH}"),
  ("OK", "done: 5 commits rewritten"),
]
ROWS = """() => [...document.querySelectorAll('#phases .phase')]
  .map((li) => [li.dataset.phase, li.dataset.state, li.querySelector('.phase-sub').textContent])"""


def test_phase_words_in_names_leave_every_row_done(desktop: Walker) -> None:
  open_run(desktop, RUN)
  desktop.page.wait_for_function(
    "() => document.querySelectorAll('#phases .phase').length === 6"
  )
  rows = desktop.page.evaluate(ROWS)
  assert [row[1] for row in rows] == ["done"] * 3 + ["skip"] + ["done"] * 2, (
    rows,
    "no check ran at the gate, so the wait is skipped",
  )
  subs = {row[0]: row[2] for row in rows}
  assert subs["pr"] == "2/2"
  assert subs["rewrite"] == "signed 5 commits"
  desktop.click("#back")
