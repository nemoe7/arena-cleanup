"""A running PR check shows an amber pulsing dot, not a spinner.

The check row in the checks modal puts the dot in the glyph slot. The live
step of its Actions job does the same. A finished row keeps its SVG glyph.
In the sidebar the amber dot of a running PR pulses too, and the other dots
stay still (docs/design.md).
"""

from __future__ import annotations

import pytest

from tests.e2e.harness import Walker
from tests.e2e.test_checks_inline import BILLING, PANE, ROW, close_modal, open_modal

pytestmark = pytest.mark.e2e

SLOT = """(slot) => {
  const dot = slot.querySelector('.dot');
  const css = dot ? getComputedStyle(dot) : {};
  const warn = getComputedStyle(document.documentElement).getPropertyValue('--warn').trim();
  const m = /^#([0-9a-f]{6})$/i.exec(warn);
  const rgb = m ? `rgb(${[0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16)).join(', ')})` : warn;
  return { dot: Boolean(dot), svg: Boolean(slot.querySelector('svg')), pulse: css.animationName || 'none',
    amber: css.backgroundColor === rgb, spin: getComputedStyle(slot).animationName };
}"""
LIVE = {"dot": True, "svg": False, "pulse": "pulse", "amber": True, "spin": "none"}
PIPELINE = ".repo-card:has-text('data-pipeline')"
SIDE_DOT = '() => getComputedStyle(document.querySelector("{row} .dot")).animationName'


def test_a_running_check_and_its_live_step_pulse_a_dot(desktop: Walker) -> None:
  page = desktop.page
  open_modal(desktop, BILLING)
  try:
    assert page.eval_on_selector("#checks-list li.running > .ico-svg", SLOT) == LIVE
    done = page.eval_on_selector("#checks-list li.passed > .ico-svg", SLOT)
    assert done["dot"] is False and done["svg"] is True, (
      "a finished row keeps its glyph"
    )
    page.click(ROW.format(name="build"))
    page.wait_for_selector(f"{PANE} .job-steps li.in_progress")
    assert (
      page.eval_on_selector(f"{PANE} .job-steps li.in_progress .ico-svg", SLOT) == LIVE
    )
  finally:
    close_modal(desktop)


def test_the_sidebar_dot_of_a_running_pr_pulses(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto()
  desktop.click(f"{PIPELINE} .repo-name")
  page.wait_for_selector(".arena-item .dot.live")
  running = "[data-branch='arena/5e1f7d2c-data-pipeline']"
  idle = "[data-branch='arena/6d8b3a4e-data-pipeline']"
  assert page.evaluate(SIDE_DOT.format(row=running)) == "pulse"
  assert page.evaluate(SIDE_DOT.format(row=idle)) == "none", "no PR, no pulse"
  desktop.click("#back")
