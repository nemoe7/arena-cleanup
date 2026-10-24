# nonemo: STE902
"""Each run phase row opens a modal with its detail.

Prepare names three steps, and PR checks and Clean up list their log lines
with stamps and durations. Rewrite and sign lists the commits after the
rewrite. Push shows the ref move, the lease, and the tags. The last row reads
Clean up.
"""

from __future__ import annotations

import json
import re

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

RUN = [
  ("INFO", "arena-cleanup 0.3.2 starting"),
  ("OK", "fetched and pruned origin"),
  ("INFO", "switching to arena/session-4 (tracking origin/arena/session-4)"),
  ("OK", "already up to date (de96315)"),
  ("INFO", "checking PR status for arena/session-4"),
  ("OK", 'check "lint": SUCCESS'),
  ("OK", "PR #57 checks ok"),
  ("INFO", "scanning 23 commit(s) as Nemo <nemo@example.com>"),
  (
    "OK",
    "history rewritten: 23 commit(s): 20 rewritten, 20 signed, 3 untouched (4.2s)",
  ),
  ("OK", "2 tag(s) now point at the rewritten commits"),
  ("INFO", "pushing (with lease) HEAD -> refs/heads/main"),
  ("OK", "pushed 2222222 to origin/main"),
  ("OK", "moved tag v1.0 11111111 -> 22222222"),
  ("OK", "updated 1 tag(s) on origin"),
  ("INFO", "returning to main"),
  ("OK", "deleted origin/arena/session-4"),
  ("OK", "done: 23 commits rewritten"),
]
MODAL = """() => {
  const dlg = document.getElementById('phase-modal');
  const body = document.getElementById('phase-body');
  return { open: dlg.open, title: document.getElementById('phase-title').textContent,
    sub: document.getElementById('phase-sub').textContent,
    steps: [...body.querySelectorAll('.step-list li')]
      .map((li) => ['.t', '.msg', '.d'].map((c) => li.querySelector(c).textContent)),
    kv: [...body.querySelectorAll('.kv dt, .kv dd')].map((e) => e.textContent),
    commits: body.querySelectorAll('.commit').length,
    link: !document.getElementById('phase-link').hidden };
}"""
PATTERN = "**/api/repos/*/jobs/latest"
PREPARE_STEPS = ["Fetched", "Located remote arena branch", "Pulled arena/session-4"]


def open_run(walker: Walker, lines: list[tuple[str, str]] | None) -> None:
  """Open infra-tools, with `lines` as its latest run when given."""
  if lines is None:
    walker.goto(1200)
    walker.click(".repo-card:has-text('infra-tools') .repo-name", 800)
    return
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
  walker.page.route(
    PATTERN,
    lambda route: route.fulfill(
      status=200, content_type="application/json", body=json.dumps(snap)
    ),
  )
  try:
    walker.goto(1200)
    walker.click(".repo-card:has-text('infra-tools') .repo-name", 800)
  finally:
    walker.page.unroute(PATTERN)


STEP_BOXES = """() => {
  const li = document.querySelector('#phase-body .step-list li');
  const box = (sel) => li.querySelector(sel).getBoundingClientRect();
  const [t, msg, d] = ['.t', '.msg', '.d'].map(box);
  return { row: li.getBoundingClientRect().width, t, msg, d };
}"""


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_a_step_row_stacks_its_text_on_a_phone_only(
  request: pytest.FixtureRequest, width: str
) -> None:
  walker: Walker = request.getfixturevalue(width)
  open_run(walker, RUN)
  open_phase(walker, "prepare")
  boxes = walker.page.evaluate(STEP_BOXES)
  stacked = boxes["msg"]["top"] > boxes["t"]["bottom"] - 1
  assert stacked == (width == "phone")
  if stacked:
    assert boxes["msg"]["width"] > boxes["row"] * 0.9, "the text takes the row"
    assert abs(boxes["d"]["top"] - boxes["t"]["top"]) < 2, (
      "the duration shares the stamp line"
    )
  close_phase(walker)
  walker.click("#back", 600)


def open_phase(walker: Walker, phase: str) -> dict:
  walker.page.click(f'.phase[data-phase="{phase}"] .phase-head')
  walker.page.wait_for_selector("#phase-modal[open]")
  return walker.page.evaluate(MODAL)


def close_phase(walker: Walker) -> None:
  walker.page.keyboard.press("Escape")
  walker.page.wait_for_function("!document.getElementById('phase-modal').open")


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_the_prepare_row_opens_its_steps_with_stamps_and_durations(
  request: pytest.FixtureRequest, width: str
) -> None:
  walker: Walker = request.getfixturevalue(width)
  open_run(walker, RUN)
  modal = open_phase(walker, "prepare")
  assert modal["title"] == "Prepare"
  assert modal["sub"] == "4.0s"
  assert [s[1] for s in modal["steps"]] == PREPARE_STEPS, (
    "three named steps, not the log"
  )
  assert all(re.fullmatch(r"\d\d:\d\d:\d\d", s[0]) for s in modal["steps"]), (
    "a clock stamp per step"
  )
  assert [s[2] for s in modal["steps"]] == ["1.0s"] * 3, (
    "each step lasts until the line that ends it"
  )
  close_phase(walker)
  walker.click("#back", 600)


def test_the_rewrite_row_lists_the_commits_under_the_counts(desktop: Walker) -> None:
  open_run(desktop, RUN)
  modal = open_phase(desktop, "rewrite")
  assert modal["sub"] == "3.0s, signed 20 commits"
  desktop.page.wait_for_selector("#phase-body .commit")
  modal = desktop.page.evaluate(MODAL)
  assert 1 <= modal["commits"] <= 20
  assert modal["steps"] == [], "the commit list replaces the steps"
  close_phase(desktop)
  desktop.click("#back", 600)


def test_the_push_row_shows_the_move_the_lease_and_the_tags(desktop: Walker) -> None:
  open_run(desktop, RUN)
  modal = open_phase(desktop, "publish")
  assert modal["title"] == "Push"
  assert modal["kv"] == [
    "Ref",
    "origin/main",
    "Move",
    "de96315 to 2222222",
    "Lease",
    "with lease on de96315",
    "Tags",
    "v1.0: 11111111 to 22222222",
  ]
  assert modal["link"] is True, "the demo origin is on GitHub"
  assert desktop.page.get_attribute("#phase-link", "href").endswith(
    "/infra-tools/commits/main"
  )
  close_phase(desktop)
  desktop.click("#back", 600)


def test_the_last_row_reads_clean_up_and_lists_its_steps(desktop: Walker) -> None:
  open_run(desktop, RUN)
  assert desktop.text('.phase[data-phase="sync"] .phase-name') == "Clean up"
  modal = open_phase(desktop, "sync")
  assert modal["title"] == "Clean up"
  assert [s[1] for s in modal["steps"]] == [text for _, text in RUN[-3:]]
  close_phase(desktop)
  desktop.click("#back", 600)


def test_idle_rows_do_not_open(desktop: Walker) -> None:
  open_run(desktop, None)
  assert desktop.count(".phase-head:disabled") == 5
