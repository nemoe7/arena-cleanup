"""Icon size tokens: the same glyph box at every width (docs/design.md)."""

from __future__ import annotations

import pytest

from tests.e2e.harness import Walker

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
# every visible button without words, with its box: nuu rule 6 wants a square
ICON_ONLY = """() => [...document.querySelectorAll('button')]
  .filter((b) => b.offsetParent !== null && !b.textContent.trim())
  .map((b) => { const r = b.getBoundingClientRect(); return [b.getAttribute('aria-label'), r.width, r.height]; })"""
OPACITY = "e => Number(getComputedStyle(e).opacity)"
BACKGROUND = "e => getComputedStyle(e).backgroundColor"
# a clean in flight hides the idle face, so the test reads a button at rest
CARD_CLEAN = ".repo-card .btn.clean:not(.running)"


def glyph_widths(walker: Walker) -> dict[str, float]:
  walker.goto()
  walker.click(".repo-card:has-text('shop-web') .repo-name")
  walker.page.wait_for_selector(".commit .sig .ico-svg")
  return {sel: walker.page.eval_on_selector(sel, BOX) for sel in GLYPHS}


def test_desktop_glyphs_sit_on_the_size_tokens(desktop: Walker) -> None:
  widths = glyph_widths(desktop)
  assert widths == GLYPHS
  assert ICON_BUTTON > BUTTON > INLINE


def test_phone_glyphs_keep_the_desktop_sizes(phone: Walker) -> None:
  assert glyph_widths(phone) == GLYPHS


def test_clean_buttons_carry_the_broom_and_sparkle_on_hover(desktop: Walker) -> None:
  desktop.goto()
  page = desktop.page
  assert page.eval_on_selector(f"{CARD_CLEAN} .ico-svg", BOX) == BUTTON
  idle = page.eval_on_selector(f"{CARD_CLEAN} .sparkles", OPACITY)
  page.hover(CARD_CLEAN)
  page.wait_for_function(
    f"() => getComputedStyle(document.querySelector('{CARD_CLEAN} .sparkles')).opacity === '1'"
  )
  assert idle == 0
  assert page.eval_on_selector(CARD_CLEAN, "e => e.innerText.trim()") == "Clean & Push"
  desktop.click(".repo-card:has-text('shop-web') .repo-name")
  assert page.eval_on_selector("#start .ico-svg", BOX) == BUTTON
  assert page.eval_on_selector("#start .sparkles", OPACITY) == 0


def hover_shift(walker: Walker) -> tuple[str, str]:
  """The reload button's background before and under the pointer."""
  walker.goto()
  before = walker.page.eval_on_selector("#repos-refresh", BACKGROUND)
  walker.page.hover("#repos-refresh")
  walker.frames()
  return before, walker.page.eval_on_selector("#repos-refresh", BACKGROUND)


def test_a_pointer_hover_tints_the_icon_button(desktop: Walker) -> None:
  before, under = hover_shift(desktop)
  assert before != under


def test_a_touch_screen_hover_leaves_the_icon_button_alone(phone: Walker) -> None:
  before, under = hover_shift(phone)
  assert before == under


def squares(walker: Walker) -> list[list[float | str]]:
  walker.goto()
  seen = walker.page.evaluate(ICON_ONLY)
  walker.click(".repo-card:has-text('data-pipeline') .repo-name")
  seen += walker.page.evaluate(ICON_ONLY)
  walker.page.goto("about:blank")
  walker.page.goto(walker.url + "#/settings")
  walker.page.wait_for_selector("#card-identity")
  walker.settle()
  return seen + walker.page.evaluate(ICON_ONLY)


def test_icon_only_buttons_are_square_on_a_desktop(desktop: Walker) -> None:
  seen = squares(desktop)
  assert {row[0] for row in seen} >= {
    "Delete arena/5e1f7d2c-data-pipeline",
    "Reload repos",
    "Settings",
  }
  assert [row for row in seen if row[1] != row[2]] == []


def test_icon_only_buttons_are_square_on_a_phone(phone: Walker) -> None:
  seen = squares(phone)
  assert [row for row in seen if row[1] != row[2]] == []
  assert min(row[1] for row in seen) >= 44, "and reach the touch size"
