"""The repo view shows the latest run again: live it streams on, done it paints at once."""

from __future__ import annotations

import pytest

from tests.e2e.harness import Demo, Walker

pytestmark = pytest.mark.e2e

ROWS = "#log .log-row"
PARKED = "still running, waiting up to"
WAIT_MS = 30000


def log_includes(walker: Walker, token: str) -> None:
  walker.page.wait_for_function(
    f"() => document.querySelector('#log').innerText.includes({token!r})",
    timeout=WAIT_MS,
  )


def phase_states(walker: Walker) -> list[str]:
  return walker.page.eval_on_selector_all(
    ".phase", "els => els.map((e) => e.dataset.state)"
  )


def test_a_finished_run_comes_back_after_a_page_reload(desktop: Walker) -> None:
  desktop.goto()
  desktop.click(".repo-card:has-text('shop-web') .repo-name")
  desktop.click('input[data-opt="dry_run"]')
  desktop.click("#start")
  status = desktop.wait_status("exit")
  rows = desktop.count(ROWS)
  assert rows > 0

  desktop.goto()
  desktop.click(".repo-card:has-text('shop-web') .repo-name")
  desktop.page.wait_for_function(
    f"() => document.querySelectorAll('{ROWS}').length === {rows}", timeout=WAIT_MS
  )
  assert desktop.status_text() == status
  assert "idle" not in phase_states(desktop)
  assert not desktop.page.eval_on_selector("#start", "e => e.disabled")


def test_a_live_run_streams_on_after_a_return_to_the_repo(
  desktop: Walker, demo: Demo, signing: None
) -> None:
  desktop.goto()
  desktop.click(".repo-card:has-text('docs-site') .repo-name")
  demo.slow_checks(True)
  try:
    box = 'input[data-opt="dry_run"]'
    if desktop.page.is_checked(box):
      desktop.click(box)
    desktop.click("#start")
    log_includes(desktop, PARKED)

    desktop.click("#back")
    assert desktop.visible("#view-dashboard")
    desktop.click(".repo-card:has-text('docs-site') .repo-name")
    assert desktop.wait_status("running") == "running"
    log_includes(desktop, PARKED)
    assert desktop.text("#start") == "Cancel", "one button, in its running state"
    assert "run" in phase_states(desktop)

    desktop.click("#start")
    assert "cancelled" in desktop.wait_status("cancelled")
  finally:
    demo.slow_checks(False)
  assert desktop.text("#start") == "Clean & Push"
  # grey from the run end until the branch state answers, then commits ahead re-arm it
  desktop.page.wait_for_function(
    "!document.getElementById('start').disabled", timeout=WAIT_MS
  )
