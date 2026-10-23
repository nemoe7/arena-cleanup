"""The page's feedback: the offline banner, the phase list, and the add bar."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from scripts.walk import Walker

REPOS_API = "**/api/repos"


@pytest.fixture
def offline(desktop: Walker) -> Iterator[Walker]:
  desktop.page.route(REPOS_API, lambda route: route.abort())
  yield desktop
  desktop.page.unroute(REPOS_API)


def test_the_offline_banner_puts_retry_on_its_own_line(offline: Walker) -> None:
  offline.goto(800)
  assert offline.visible("#offline-banner #retry")
  lines = offline.text("#offline-banner").strip().splitlines()
  assert lines[0].endswith("then retry.") and lines[-1] == "Retry"
  lead = offline.page.eval_on_selector(
    "#offline-banner b", "e => e.getBoundingClientRect().bottom"
  )
  button = offline.page.eval_on_selector("#retry", "e => e.getBoundingClientRect().top")
  assert button >= lead, "the button shares a line with the text"


def test_a_failed_pr_check_fails_the_pr_phase_alone(desktop: Walker) -> None:
  desktop.goto(1200)
  desktop.click(".repo-card:has-text('billing-api')", 800)
  desktop.click('input[data-opt="dry_run"]', 0)
  desktop.click("#start", 0)
  assert "exit 0" not in desktop.wait_status("exit")
  states = desktop.page.eval_on_selector_all(
    ".phase", "els => els.map((e) => [e.dataset.phase, e.dataset.state])"
  )
  assert dict(states) == {
    "prepare": "done",
    "pr": "fail",
    "rewrite": "skip",
    "publish": "skip",
    "sync": "skip",
  }
