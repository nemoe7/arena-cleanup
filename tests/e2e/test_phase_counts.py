"""The phase rows carry the engine's counts, and no hint text."""

from __future__ import annotations

import json
import re

import pytest

from scripts.walk import Demo, Walker

pytestmark = pytest.mark.e2e

WAIT_MS = 30000


def row_texts(walker: Walker) -> dict[str, str]:
  pairs = walker.page.eval_on_selector_all(
    ".phase",
    "els => els.map((e) => [e.dataset.phase, e.querySelector('.phase-sub').textContent])",
  )
  return dict(pairs)


def test_idle_rows_show_only_their_names(desktop: Walker) -> None:
  desktop.goto(1200)
  # no e2e test runs infra-tools, so its view has no latest run to show
  desktop.click(".repo-card:has-text('infra-tools') .repo-name", 800)
  assert set(row_texts(desktop).values()) == {""}


def test_a_dry_run_counts_checks_commits_and_tags(desktop: Walker) -> None:
  desktop.goto(1200)
  desktop.click(".repo-card:has-text('shop-web') .repo-name", 800)
  desktop.click('input[data-opt="dry_run"]', 0)
  desktop.click("#start", 0)
  desktop.wait_status("exit")
  rows = row_texts(desktop)
  assert rows["prepare"] == ""
  assert rows["pr"] == "4/4"
  assert re.fullmatch(r"would sign \d+ commits", rows["rewrite"])
  assert rows["publish"] == "", "no tag, no text"
  assert rows["sync"] == ""


# a real run's lines, as the engine writes them, up to the tag push
REAL_RUN = [
  ("INFO", "arena-cleanup 0.2.4 on main"),
  ("OK", 'check "unit": pass'),
  ("WARN", 'check "e2e": running'),
  ("OK", 'check "e2e": pass'),
  ("INFO", "scanning 23 commit(s) as Nemo <nemo@example.com>"),
  ("INFO", "rewriting... 50% (12/23) - 10 rewritten"),
  (
    "OK",
    "history rewritten: 23 commit(s): 20 rewritten, 20 signed, 3 untouched (4.2s)",
  ),
  ("OK", "2 tag(s) now point at the rewritten commits"),
  ("OK", "moved tag v1.0 11111111 -> 22222222"),
  ("OK", "updated 2 tag(s) on origin"),
]


def painted(walker: Walker, lines: list[tuple[str, str]]) -> dict[str, str]:
  """The rows after the page reattaches to a finished run made of `lines`."""
  snap = {
    "id": "fake",
    "status": "done",
    "exit": 0,
    "cancelled": False,
    "elapsed": 4.2,
    "lines": [
      {"t": 1_700_000_000 + i, "text": f"2026-10-23T10:00:{i:02d}+0000 {level} {text}"}
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
    return row_texts(walker)
  finally:
    walker.page.unroute(pattern)


def test_a_real_run_reads_signing_then_signed_and_pushed(desktop: Walker) -> None:
  rows = painted(desktop, REAL_RUN[:6])
  assert rows["pr"] == "2/2"
  assert rows["rewrite"] == "signing 10/23"
  assert rows["publish"] == ""

  rows = painted(desktop, REAL_RUN[:8])
  assert rows["rewrite"] == "signed 20 commits"
  assert rows["publish"] == "moving 2 tags"

  rows = painted(desktop, REAL_RUN[:9])
  assert rows["publish"] == "pushing 2 tags"

  rows = painted(desktop, REAL_RUN)
  assert rows["publish"] == "pushed 2 tags"


def test_the_checks_row_counts_passed_of_total(desktop: Walker) -> None:
  rows = painted(desktop, REAL_RUN[:3])
  assert rows["pr"] == "1/2", "a running check counts in the total alone"
  rows = painted(desktop, REAL_RUN[:5])
  assert rows["pr"] == "2/2"
  assert rows["rewrite"] == "collecting 23 commits"


def test_a_waiting_check_shows_as_live(desktop: Walker, demo: Demo) -> None:
  desktop.goto(1200)
  desktop.click(".repo-card:has-text('docs-site') .repo-name", 800)
  demo.slow_checks(True)
  try:
    box = 'input[data-opt="dry_run"]'
    if desktop.page.is_checked(box):
      desktop.click(box, 150)
    desktop.click("#start", 0)
    desktop.page.wait_for_function(
      "() => document.querySelector('.phase[data-phase=\"pr\"] .phase-sub')"
      ".textContent === '0/1'",
      timeout=WAIT_MS,
    )
  finally:
    demo.slow_checks(False)
    desktop.click("#start", 0)
    desktop.wait_status("cancelled")
