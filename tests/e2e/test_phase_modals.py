# nonemo: STE902
"""Each run phase row opens a modal with its detail.

Prepare and Clean up name their steps as rows like the job steps of a check.
Each row holds a state glyph, the name, and the duration. PR checks shows the
checks the run kept, or names its steps without them. Rewrite and sign lists
the commits after the rewrite, and Push shows the ref move, the lease, and the
tags.
"""

from __future__ import annotations

import json

import pytest

from tests.e2e.harness import Walker

pytestmark = pytest.mark.e2e

RUN = [
  ("INFO", "arena-cleanup 0.3.8 starting"),
  ("OK", "fetched and pruned origin"),
  (
    "INFO",
    "switching to arena/4c3a9b5f-infra-tools (tracking origin/arena/4c3a9b5f-infra-tools)",
  ),
  ("OK", "already up to date (de96315)"),
  ("INFO", "scanning 23 commit(s) as Nemo <nemo@example.com>"),
  (
    "OK",
    "history rewritten: 23 commit(s): 20 rewritten, 20 signed, 3 untouched (4.2s)",
  ),
  ("OK", "2 tag(s) now point at the rewritten commits"),
  ("INFO", "checking PR status for arena/4c3a9b5f-infra-tools"),
  ("OK", 'check "lint": SUCCESS'),
  ("OK", "PR #57 checks ok"),
  ("INFO", "pushing (with lease) HEAD -> refs/heads/main"),
  ("OK", "pushed 2222222 to origin/main"),
  ("OK", "moved tag v1.0 11111111 -> 22222222"),
  ("OK", "updated 1 tag(s) on origin"),
  ("INFO", "returning to main"),
  ("OK", "deleted origin/arena/4c3a9b5f-infra-tools"),
  ("OK", "done: 23 commits rewritten"),
]
MODAL = """() => {
  const dlg = document.getElementById('modal');
  const body = document.getElementById('modal-body');
  return { open: dlg.open, title: document.getElementById('modal-title').textContent,
    sub: document.getElementById('modal-sub').textContent,
    steps: [...body.querySelectorAll('.step-list li')]
      .map((li) => [li.className, ...['.name', '.d'].map((c) => li.querySelector(c).textContent)]),
    kv: [...body.querySelectorAll('.kv dt, .kv dd')].map((e) => e.textContent),
    commits: body.querySelectorAll('.commit').length,
    link: Boolean(document.getElementById('phase-link')) && !document.getElementById('phase-link').hidden,
    foot: [...document.querySelectorAll('#modal .modal-actions > *')]
      .filter((e) => !e.hidden && !e.parentElement.hidden).map((e) => e.textContent.trim()) };
}"""
PATTERN = "**/api/repos/*/jobs/latest"
JOB = "**/api/jobs/fake"
PREPARE_STEPS = [
  "Fetched",
  "Located remote arena branch",
  "Pulled arena/4c3a9b5f-infra-tools",
]


def open_run(
  walker: Walker,
  lines: list[tuple[str, str]] | None,
  status: str = "done",
  pr: dict | None = None,
) -> None:
  """Open infra-tools, with `lines` as its latest run when given.

  A `running` run answers the job poll too, since the live page reads its
  lines there once the event stream fails. `pr` is the PR checks the run kept.
  """
  if lines is None:
    walker.goto()
    walker.click(".repo-card:has-text('infra-tools') .repo-name")
    return
  snap = {
    "id": "fake",
    "status": status,
    "exit": 0 if status == "done" else None,
    "cancelled": False,
    "elapsed": float(len(lines) - 1),
    "lines": [
      {"t": 1_700_000_000 + i, "text": f"2026-10-24T10:00:{i:02d}+0000 {level} {text}"}
      for i, (level, text) in enumerate(lines)
    ],
    "pr": pr,
  }
  patterns = [PATTERN] + ([JOB] if status == "running" else [])
  for pattern in patterns:
    walker.page.route(
      pattern,
      lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(snap)
      ),
    )
  try:
    walker.goto()
    walker.click(".repo-card:has-text('infra-tools') .repo-name")
  finally:
    walker.page.unroute(PATTERN)


STEP_ROW = """() => {
  const li = document.querySelector('#modal-body .step-list li');
  const mid = (e) => { const b = e.getBoundingClientRect(); return b.top + b.height / 2; };
  const glyph = li.querySelector('.ico-svg');
  const want = getComputedStyle(document.documentElement).getPropertyValue('--ok').trim();
  const probe = document.createElement('span');
  probe.style.color = want;
  document.body.append(probe);
  const ok = getComputedStyle(probe).color;
  probe.remove();
  return { parts: [...li.children].map((e) => e.className.split(' ')[0]),
    stamp: Boolean(li.querySelector('.t')),
    oneLine: Math.max(mid(glyph), mid(li.querySelector('.name')), mid(li.querySelector('.d')))
      - Math.min(mid(glyph), mid(li.querySelector('.name')), mid(li.querySelector('.d'))) < 2,
    check: Boolean(glyph.querySelector('svg')), colour: getComputedStyle(glyph).color, ok };
}"""


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_a_step_row_reads_glyph_name_and_duration_on_one_line(
  request: pytest.FixtureRequest, width: str
) -> None:
  """The row matches a job step of a check at both widths, with no clock stamp."""
  walker: Walker = request.getfixturevalue(width)
  open_run(walker, RUN)
  open_phase(walker, "prepare")
  row = walker.page.evaluate(STEP_ROW)
  assert row["parts"] == ["ico-svg", "name", "d"]
  assert not row["stamp"], "the clock stamp is gone"
  assert row["oneLine"], "glyph, name, and duration share one line"
  assert row["check"] and row["colour"] == row["ok"], "a green check per done step"
  close_phase(walker)
  walker.click("#back")


def open_phase(walker: Walker, phase: str) -> dict:
  walker.page.click(f'.phase[data-phase="{phase}"] .phase-head')
  walker.page.wait_for_selector("#modal[open]")
  return walker.page.evaluate(MODAL)


def close_phase(walker: Walker) -> None:
  walker.page.keyboard.press("Escape")
  walker.page.wait_for_function("!document.getElementById('modal').open")


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
  assert all(s[0] == "ok" for s in modal["steps"]), "a done glyph per step"
  assert [s[2] for s in modal["steps"]] == ["1.0s"] * 3, (
    "each step lasts until the line that ends it"
  )
  close_phase(walker)
  walker.click("#back")


def test_the_rewrite_row_lists_the_commits_under_the_counts(desktop: Walker) -> None:
  open_run(desktop, RUN)
  modal = open_phase(desktop, "rewrite")
  assert modal["sub"] == "3.0s, signed 20 commits"
  desktop.page.wait_for_selector("#modal-body .commit")
  modal = desktop.page.evaluate(MODAL)
  assert 1 <= modal["commits"] <= 20
  assert modal["steps"] == [], "the commit list replaces the steps"
  close_phase(desktop)
  desktop.click("#back")


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
  assert modal["foot"] == ["Open"], "the foot holds Open alone, the head x closes"
  assert desktop.page.get_attribute("#phase-link", "href").endswith(
    "/infra-tools/commits/main"
  )
  close_phase(desktop)
  desktop.click("#back")


def test_the_last_row_reads_clean_up_and_names_its_steps(desktop: Walker) -> None:
  open_run(desktop, RUN)
  assert desktop.text('.phase[data-phase="sync"] .phase-name') == "Clean up"
  modal = open_phase(desktop, "sync")
  assert modal["title"] == "Clean up"
  assert [s[1] for s in modal["steps"]] == [
    "Returned to main",
    "Deleted origin/arena/4c3a9b5f-infra-tools",
    "Done, 23 commits rewritten",
  ], "named steps, not the log lines"
  assert modal["foot"] == [], "no link, no foot"
  close_phase(desktop)
  desktop.click("#back")


CHECKS = """() => ({
  rows: [...document.querySelectorAll('#modal .check-list li')]
    .map((li) => [li.className, li.querySelector('.name').textContent, li.querySelector('.phrase').textContent]),
  view: document.getElementById('modal').dataset.view })"""


# the checks the run kept: one check, a name the live PR of the demo does not have
RUN_PR = {
  "branch": "arena/4c3a9b5f-infra-tools",
  "number": 57,
  "title": "chore: pin the base image",
  "url": "https://github.com/demo/infra-tools/pull/57",
  "total": 1,
  "passed": 1,
  "failed": 0,
  "running": 0,
  "state": "passing",
  "checks": [
    {
      "name": "lint",
      "state": "SUCCESS",
      "result": "passed",
      "url": "",
      "workflow": "",
      "started": "",
      "completed": "",
    }
  ],
}


def test_the_pr_checks_row_shows_the_checks_the_run_kept(desktop: Walker) -> None:
  """The row opens the pill rows of the PR as the run read them, not today's."""
  open_run(desktop, RUN, pr=RUN_PR)
  head = '.phase[data-phase="pr"] .phase-head'
  assert desktop.page.get_attribute(head, "title") == "Show PR checks"
  modal = open_phase(desktop, "pr")
  assert modal["title"] == "PR #57 checks"
  assert modal["sub"].endswith(": 1/1 passed when the run read them")
  checks = desktop.page.evaluate(CHECKS)
  assert checks["view"] == "checks"
  assert checks["rows"] == [["passed", "lint", "Successful"]], (
    "the kept check, not the live pill"
  )
  assert modal["steps"] == [], "no log lines"
  assert modal["foot"] == ["Open PR"]
  close_phase(desktop)
  desktop.click("#back")


def test_the_pr_checks_row_names_its_steps_when_the_run_kept_no_checks(
  desktop: Walker,
) -> None:
  """A run before the snapshot, or one without a PR, keeps the step names."""
  open_run(desktop, RUN)
  modal = open_phase(desktop, "pr")
  assert modal["title"] == "PR checks"
  assert [s[1] for s in modal["steps"]] == ["PR #57 checks passed"]
  assert desktop.page.evaluate(CHECKS)["rows"] == []
  assert modal["foot"] == [], "no link, no foot"
  close_phase(desktop)
  desktop.click("#back")


GROWING = [
  ("INFO", "arena-cleanup 0.3.6 starting"),
  ("OK", "fetched and pruned origin"),
  ("INFO", "switching to arena/elsewhere (tracking origin/arena/elsewhere)"),
  ("OK", "already up to date (de96315)"),
  ("INFO", "checking PR status for arena/elsewhere"),
  ("INFO", "found PR #119"),
  ("WARN", 'check "Repository Quality": IN_PROGRESS'),
  ("OK", 'check "Review Dependencies": SUCCESS'),
  ("INFO", "1 check(s) still running, waiting up to 15m00s (polling every 1s)"),
  ("OK", 'check "Repository Quality": SUCCESS'),
  ("OK", 'check "CodeQL": SUCCESS'),
  ("INFO", "all 2 check(s) finished after 2m39s"),
  ("OK", "PR #119 checks ok"),
  ("INFO", "scanning 2 commit(s) as Nemo <nemo@example.com>"),
  ("OK", "history rewritten: 2 commit(s): 1 rewritten, 1 signed, 1 untouched (0.3s)"),
  ("INFO", "pushing (with lease) HEAD -> refs/heads/main"),
  ("OK", "pushed 8ffa87d to origin/main"),
  ("INFO", "returning to main"),
  ("OK", "done"),
]


WAITED = [
  ("INFO", "arena-cleanup 0.3.8 starting"),
  ("OK", "fetched and pruned origin"),
  ("INFO", "switching to arena/elsewhere (tracking origin/arena/elsewhere)"),
  ("OK", "already up to date (de96315)"),
  ("INFO", "scanning 2 commit(s) as Nemo <nemo@example.com>"),
  ("OK", "history rewritten: 2 commit(s): 1 rewritten, 1 signed, 1 untouched (0.3s)"),
  ("INFO", "checking PR status for arena/elsewhere"),
  ("INFO", "found PR #119"),
  ("WARN", 'check "Repository Quality": IN_PROGRESS'),
  ("OK", 'check "Review Dependencies": SUCCESS'),
  ("INFO", "1 check(s) still running, waiting up to 15m00s (polling every 1s)"),
  ("INFO", "waiting for PR #119 checks (1 still running)"),
  ("OK", 'check "Repository Quality": SUCCESS'),
  ("OK", 'check "CodeQL": SUCCESS'),
  ("INFO", "all 3 check(s) finished after 2m39s"),
  ("OK", "PR #119 checks ok"),
  ("INFO", "pushing (with lease) HEAD -> refs/heads/main"),
  ("OK", "pushed 8ffa87d to origin/main"),
  ("INFO", "returning to main"),
  ("OK", "done"),
]


def test_the_gate_after_the_rewrite_waits_inside_the_pr_checks_row(
  desktop: Walker,
) -> None:
  """The engine rewrites first, then reads and waits on the checks in one row."""
  open_run(desktop, WAITED)
  rows = desktop.page.evaluate(
    """() => [...document.querySelectorAll('#phases .phase')]
      .map((li) => [li.dataset.phase, li.dataset.state, li.querySelector('.phase-sub').textContent])"""
  )
  assert [r[0] for r in rows] == ["prepare", "rewrite", "pr", "publish", "sync"]
  assert [r[1] for r in rows] == ["done"] * 5
  subs = {r[0]: r[2] for r in rows}
  assert subs["pr"] == "3/3"
  modal = open_phase(desktop, "pr")
  assert [s[1] for s in modal["steps"]] == [
    "Found PR #119",
    "1 check still running",
    "All 3 checks finished",
    "PR #119 checks passed",
  ]
  close_phase(desktop)
  desktop.click("#back")


def test_a_running_wait_names_the_running_checks_in_the_pr_row(desktop: Walker) -> None:
  open_run(desktop, WAITED[:12], status="running")
  desktop.page.wait_for_selector('.phase[data-phase="pr"][data-state="run"]')
  assert desktop.text('.phase[data-phase="pr"] .phase-sub') == "1/2"
  modal = open_phase(desktop, "pr")
  assert [s[1] for s in modal["steps"]] == [
    "Found PR #119",
    "1 check still running",
    "Waiting for 1 running check…",
  ]
  assert [s[0] for s in modal["steps"]] == ["ok", "ok", "run"], (
    "the wait is the open step"
  )
  close_phase(desktop)
  desktop.page.unroute(JOB)
  desktop.click("#back")


def test_checks_added_during_the_wait_count_in_the_pr_steps(desktop: Walker) -> None:
  """An older engine froze its total at the first read. The steps count check lines."""
  open_run(desktop, GROWING)
  assert desktop.text('.phase[data-phase="pr"] .phase-sub') == "3/3"
  modal = open_phase(desktop, "pr")
  assert [s[1] for s in modal["steps"]] == [
    "Found PR #119",
    "1 check still running",
    "All 3 checks finished",
    "PR #119 checks passed",
  ]
  close_phase(desktop)
  desktop.click("#back")


def test_a_running_rewrite_names_the_collected_commits_and_the_open_step(
  desktop: Walker,
) -> None:
  open_run(desktop, RUN[:5], status="running")
  desktop.page.wait_for_selector('.phase[data-phase="rewrite"][data-state="run"]')
  modal = open_phase(desktop, "rewrite")
  assert [s[1] for s in modal["steps"]] == ["Collected 23 commits", "Signing…"]
  assert [s[0] for s in modal["steps"]] == ["ok", "run"], "the open step is live"
  assert desktop.count("#modal-body .step-list .run .ico-svg .dot") == 1
  close_phase(desktop)
  desktop.page.unroute(JOB)
  desktop.click("#back")


def test_idle_rows_do_not_open(desktop: Walker) -> None:
  open_run(desktop, None)
  assert desktop.count(".phase-head:disabled") == 5


RUN_GLYPH = """() => {
  const ico = document.querySelector('.phase[data-state="run"] .phase-ico');
  const style = getComputedStyle(ico);
  const warn = getComputedStyle(document.documentElement).getPropertyValue('--warn').trim();
  const probe = document.createElement('span');
  probe.style.color = warn;
  document.body.append(probe);
  const want = getComputedStyle(probe).color;
  probe.remove();
  const dot = ico.querySelector('.ico-svg > .dot');
  return { color: style.color, want, svg: Boolean(ico.querySelector('svg')), dot: Boolean(dot),
    animation: dot ? getComputedStyle(dot).animationName : 'none',
    amber: dot ? getComputedStyle(dot).backgroundColor === want : false };
}"""


def test_a_running_row_pulses_an_amber_dot(desktop: Walker) -> None:
  """The live row is an amber state, so its glyph slot holds the pulsing dot."""
  open_run(desktop, RUN[:5], status="running")
  desktop.page.wait_for_selector('.phase[data-state="run"] .phase-ico .dot')
  glyph = desktop.page.evaluate(RUN_GLYPH)
  assert glyph["color"] == glyph["want"], "the running slot is amber"
  assert glyph["dot"] and glyph["amber"] and not glyph["svg"], "a dot, no glyph"
  assert glyph["animation"] == "pulse"
  desktop.page.unroute(JOB)
  desktop.click("#back")
