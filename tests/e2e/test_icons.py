"""Icon size tokens: the same glyph box at every width (docs/design.md)."""

from __future__ import annotations

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

INLINE = 14.0
BUTTON = 16.0
ICON_BUTTON = 18.0
GLYPHS = {
  ".brand .ico-svg": ICON_BUTTON,
  "#back .ico-svg": BUTTON,
  "#copy .ico-svg": ICON_BUTTON,
  ".phase-ico .ico-svg": BUTTON,
  ".commit .sig .ico-svg": INLINE,
  ".commit .avatar.none .ico-svg": INLINE,
}
BOX = "e => e.getBoundingClientRect().width"
OPACITY = "e => Number(getComputedStyle(e).opacity)"
CARD_CLEAN = ".repo-card .btn.clean"


def glyph_widths(walker: Walker) -> dict[str, float]:
  walker.goto(1200)
  walker.click(".repo-card:has-text('shop-web') .repo-name", 800)
  walker.page.wait_for_selector(".commit .sig .ico-svg")
  return {sel: walker.page.eval_on_selector(sel, BOX) for sel in GLYPHS}


def test_desktop_glyphs_sit_on_the_size_tokens(desktop: Walker) -> None:
  widths = glyph_widths(desktop)
  assert widths == GLYPHS
  assert ICON_BUTTON > BUTTON > INLINE


def test_phone_glyphs_keep_the_desktop_sizes(phone: Walker) -> None:
  assert glyph_widths(phone) == GLYPHS


def test_clean_buttons_carry_the_broom_and_sparkle_on_hover(desktop: Walker) -> None:
  desktop.goto(1200)
  page = desktop.page
  assert page.eval_on_selector(f"{CARD_CLEAN} .ico-svg", BOX) == BUTTON
  idle = page.eval_on_selector(f"{CARD_CLEAN} .sparkles", OPACITY)
  page.hover(CARD_CLEAN)
  page.wait_for_function(
    f"() => getComputedStyle(document.querySelector('{CARD_CLEAN} .sparkles')).opacity === '1'"
  )
  assert idle == 0
  assert (
    page.eval_on_selector(CARD_CLEAN, "e => e.textContent.trim()") == "Clean & Push"
  )
  desktop.click(".repo-card:has-text('shop-web') .repo-name", 800)
  assert page.eval_on_selector("#start .ico-svg", BOX) == BUTTON
  assert page.eval_on_selector("#start .sparkles", OPACITY) == 0
