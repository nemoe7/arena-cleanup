"""A repo opened during its own run shows Cancel from the first paint.

The list flags a repo with a live job. The repo view reads that flag as it
opens. The button is Cancel, disabled until the job id arrives, and the status
reads running. The latest-run answer then attaches the stream and enables the
button, so Clean & Push never shows in between (docs/design.md).
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e.harness import Demo, Walker

pytestmark = pytest.mark.e2e

REPO = "docs-site"
CARD = f".repo-card:has-text('{REPO}')"
LATEST = "**/api/repos/*/jobs/latest"
BUTTON = """() => {
  const btn = document.getElementById('start');
  return { label: btn.innerText.trim(), state: btn.dataset.state, disabled: btn.disabled,
    primary: btn.classList.contains('primary'),
    status: document.getElementById('status').className.split(' ').pop() };
}"""


def release(held: list[Any]) -> None:
  """Let every held answer through."""
  while held:
    held.pop().continue_()


def test_an_open_during_a_run_paints_cancel_before_the_answer(
  desktop: Walker, demo: Demo, signing: None
) -> None:
  page = desktop.page
  held: list[Any] = []

  desktop.goto()
  desktop.click(f"{CARD} .repo-name")
  demo.slow_checks(True)
  try:
    box = 'input[data-opt="dry_run"]'
    if page.is_checked(box):
      desktop.click(box)
    desktop.click("#start")
    assert desktop.wait_status("running") == "running"
    desktop.click("#back")
    page.wait_for_selector(f"{CARD} button.clean.running")

    # the latest-run answer waits until the first paint is read
    page.route(LATEST, lambda r: held.append(r))
    desktop.click(f"{CARD} .repo-name")
    first = page.evaluate(BUTTON)
    assert first["label"] == "Cancel", "no Clean & Push before the answer"
    assert first["state"] == "attaching" and first["disabled"] is True
    assert first["primary"] is False and first["status"] == "running"
    assert held, "the answer is still held"
    release(held)
    page.wait_for_function(
      "document.getElementById('start').dataset.state === 'running'"
    )
    page.unroute(LATEST)
    after = page.evaluate(BUTTON)
    assert after["label"] == "Cancel" and after["disabled"] is False
    desktop.click("#start")
    assert "cancelled" in desktop.wait_status("cancelled")
  finally:
    release(held)
    demo.slow_checks(False)
