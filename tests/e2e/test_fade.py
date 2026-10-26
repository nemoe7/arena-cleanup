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


BAR_FADE = """() => {
  const bar = document.getElementById('tabbar');
  const s = getComputedStyle(bar, '::before');
  return { height: s.height, image: s.backgroundImage, animation: s.animationName,
    opacity: parseFloat(s.opacity), bottom: parseFloat(s.bottom),
    bar: bar.getBoundingClientRect().height,
    supported: CSS.supports('animation-timeline: scroll(root)') };
}"""


def test_the_phone_page_fades_behind_the_bottom_bar(phone: Walker) -> None:
  """The nuu floating-overlay fade: 36 px above the bar, lifted at the page end."""
  phone.goto(1200)
  phone.click(".repo-card:has-text('shop-web') .repo-name", 800)
  page = phone.page
  page.wait_for_selector("#commits .commit")
  fade = page.evaluate(BAR_FADE)
  assert fade["height"] == "36px"
  assert fade["bottom"] == fade["bar"], "the strip sits on the top edge of the bar"
  assert "linear-gradient" in fade["image"]
  if fade["supported"]:
    assert fade["animation"] == "tab-fade"
    assert fade["opacity"] == 1, "the fade shows while the page end is away"
    page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
    page.wait_for_function(
      "() => parseFloat(getComputedStyle(document.getElementById('tabbar'), '::before').opacity) === 0"
    )
  phone.click("#back", 600)


def test_the_compact_stamp_sits_in_the_tabular_monospace_face(desktop: Walker) -> None:
  desktop.goto(1200)
  page = desktop.page
  page.wait_for_selector(".repo-since")
  face = page.eval_on_selector(
    ".repo-since",
    "e => { const s = getComputedStyle(e); return [s.fontFamily, s.fontVariantNumeric]; }",
  )
  assert "Monaspace Neon" in face[0]
  assert face[1] == "tabular-nums"
