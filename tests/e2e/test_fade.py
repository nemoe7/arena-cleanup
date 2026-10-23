"""Scroll-edge fade: the commit list and the log mask 12 px at a scrolled edge."""

from __future__ import annotations

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

PANELS = ("#commits", "#log")
EDGE_FADE = 12.0
MASK = "e => getComputedStyle(e).maskImage"
EDGE_START = "e => parseFloat(getComputedStyle(e).getPropertyValue('--edge-start'))"
EDGE_END = "e => parseFloat(getComputedStyle(e).getPropertyValue('--edge-end'))"


def test_the_scroll_panels_fade_at_their_edges(desktop: Walker) -> None:
  desktop.goto(1200)
  desktop.click(".repo-card:has-text('shop-web') .repo-name", 800)
  page = desktop.page
  page.wait_for_selector("#commits .commit")
  for sel in PANELS:
    assert "linear-gradient" in page.eval_on_selector(sel, MASK), sel
  assert page.eval_on_selector(".main-col", MASK) == "none"
  assert page.eval_on_selector(".sidebar", MASK) == "none"

  commits = "#commits"
  assert page.eval_on_selector(commits, "e => e.scrollHeight > e.clientHeight")
  assert page.eval_on_selector(commits, EDGE_START) == 0
  assert page.eval_on_selector(commits, EDGE_END) == EDGE_FADE
  page.eval_on_selector(commits, "e => { e.scrollTop = e.scrollHeight; }")
  page.wait_for_function(
    "() => getComputedStyle(document.querySelector('#commits'))"
    ".getPropertyValue('--edge-end') === '0px'"
  )
  assert page.eval_on_selector(commits, EDGE_START) == EDGE_FADE
  assert page.eval_on_selector(commits, EDGE_END) == 0
