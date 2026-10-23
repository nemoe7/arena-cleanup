"""The phase rows carry the engine's counts, and no hint text."""

from __future__ import annotations

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
  desktop.click(".repo-card:has-text('infra-tools')", 800)
  assert set(row_texts(desktop).values()) == {""}


def test_a_dry_run_counts_checks_commits_and_tags(desktop: Walker) -> None:
  desktop.goto(1200)
  desktop.click(".repo-card:has-text('shop-web')", 800)
  desktop.click('input[data-opt="dry_run"]', 0)
  desktop.click("#start", 0)
  desktop.wait_status("exit")
  rows = row_texts(desktop)
  assert rows["prepare"] == ""
  assert rows["pr"] == "4 checks"
  assert re.fullmatch(r"\d+ of 23 commits to rewrite", rows["rewrite"])
  assert rows["publish"] == "0 tags to move"
  assert rows["sync"] == ""


def test_a_waiting_check_shows_as_live(desktop: Walker, demo: Demo) -> None:
  desktop.goto(1200)
  desktop.click(".repo-card:has-text('docs-site')", 800)
  demo.slow_checks(True)
  try:
    box = 'input[data-opt="dry_run"]'
    if desktop.page.is_checked(box):
      desktop.click(box, 150)
    desktop.click("#start", 0)
    desktop.page.wait_for_function(
      "() => document.querySelector('.phase[data-phase=\"pr\"] .phase-sub')"
      ".textContent === '1 check, 1 running'",
      timeout=WAIT_MS,
    )
  finally:
    demo.slow_checks(False)
    desktop.click("#start", 0)
    desktop.wait_status("cancelled")
