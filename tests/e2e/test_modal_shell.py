"""One dialog shell serves the checks, the phase detail, and the delete confirm.

The page holds a single `dialog`. Each view mounts its template into the body
and the actions row. It names itself in `data-view` and sets the width class.
The opening focus follows the view: the body for checks and phase, Cancel for
the delete confirm (docs/design.md).
"""

from __future__ import annotations

import pytest

from scripts.walk import Walker

from .test_phase_modals import RUN, open_phase, open_run

pytestmark = pytest.mark.e2e

SHELL = """() => {
  const dlg = document.getElementById('modal');
  return { dialogs: document.querySelectorAll('dialog').length, open: dlg.open,
    view: dlg.dataset.view, wide: dlg.classList.contains('wide'),
    title: document.getElementById('modal-title').textContent,
    sub: document.getElementById('modal-sub').hidden ? null : document.getElementById('modal-sub').textContent,
    focus: document.activeElement.id || document.activeElement.textContent.trim(),
    actions: [...document.querySelectorAll('#modal-actions > *')].map((e) => e.textContent.trim()) };
}"""
CLOSED = "!document.getElementById('modal').open"


def test_the_three_views_share_one_dialog(desktop: Walker) -> None:
  page = desktop.page
  open_run(desktop, RUN)
  assert page.evaluate(SHELL)["dialogs"] == 1, "one dialog element in the page"

  open_phase(desktop, "prepare")
  phase = page.evaluate(SHELL)
  assert phase["view"] == "phase" and phase["wide"] is True
  assert phase["title"] == "Prepare" and phase["sub"] == "4.0s"
  assert phase["focus"] == "modal-body", "the body takes the opening focus"
  page.keyboard.press("Escape")
  page.wait_for_function(CLOSED)

  page.click(".arena-del")
  page.wait_for_selector("#modal[open]")
  confirm = page.evaluate(SHELL)
  assert confirm["view"] == "confirm-delete" and confirm["wide"] is False
  assert confirm["title"] == "Delete arena branch" and confirm["sub"] is None
  assert confirm["focus"] == "Cancel", "Cancel takes the opening focus"
  assert confirm["actions"] == ["Cancel", "Delete"]
  assert len(desktop.text("#confirm-branch")) > 0, "the branch rides in the body"
  page.keyboard.press("Escape")
  page.wait_for_function(CLOSED)

  page.click(".arena-checks")
  page.wait_for_selector("#modal[open]")
  checks = page.evaluate(SHELL)
  assert checks["view"] == "checks" and checks["wide"] is True
  assert checks["title"].startswith("PR #") and checks["sub"] is not None
  assert checks["focus"] == "modal-body"
  assert checks["actions"] == ["Open PR"], "the last view's actions are gone"
  page.keyboard.press("Escape")
  page.wait_for_function(CLOSED)
  desktop.click("#back", 600)
