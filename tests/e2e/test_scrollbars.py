"""Scrollbars follow the nuu recipe, and only the scrolling views reserve a gutter.

Chromium knows `::-webkit-scrollbar`, so the standard `scrollbar-width` stays
`auto` there and the drawn 10 px thumb shows. The page root reserves no
gutter, since on a desktop the views scroll and the page never does. So a
view spans the whole window. The thumb is the recipe colour and highlights
under keyboard navigation alone (docs/design.md).
"""

from __future__ import annotations

import pytest

from tests.e2e.harness import Walker

pytestmark = pytest.mark.e2e

GUTTERS = """() => ({
  root: getComputedStyle(document.documentElement).scrollbarGutter,
  view: getComputedStyle(document.getElementById('view-dashboard')).scrollbarGutter,
  width: getComputedStyle(document.getElementById('view-dashboard')).scrollbarWidth,
  viewW: document.getElementById('view-dashboard').offsetWidth,
  windowW: innerWidth,
})"""
THUMB = "rgb(48, 46, 44)"
THUMB_STYLE = """() => {
  const view = document.getElementById('view-dashboard');
  const thumb = getComputedStyle(view, '::-webkit-scrollbar-thumb');
  const flat = (list) => [...list].flatMap((r) => (r.selectorText ? [r] : flat(r.cssRules || [])));
  const rules = flat([...document.styleSheets].flatMap((s) => [...s.cssRules]));
  const hover = rules.filter((r) => r.selectorText && r.selectorText.includes('::-webkit-scrollbar-thumb:hover'));
  return {
    fill: thumb.backgroundColor,
    radius: thumb.borderRadius,
    hover: hover.map((r) => r.selectorText.split(',').map((x) => x.trim())).flat(),
  };
}"""


def test_the_root_reserves_no_gutter_and_chromium_keeps_the_drawn_thumb(
  desktop: Walker,
) -> None:
  desktop.goto()
  got = desktop.page.evaluate(GUTTERS)
  assert got["root"] == "auto", "the page root reserves no gutter"
  assert got["view"] == "stable", "a scrolling view keeps its gutter"
  assert got["width"] == "auto", "the standard width stays off where WebKit draws"
  assert got["viewW"] == got["windowW"], "the view spans the whole window"


def test_the_thumb_is_the_recipe_colour_and_highlights_for_the_keyboard_alone(
  desktop: Walker,
) -> None:
  desktop.goto()
  got = desktop.page.evaluate(THUMB_STYLE)
  assert got["fill"] == THUMB, "the thumb is the recipe #302e2c"
  assert got["radius"] == "8px"
  assert got["hover"], "a hover rule exists for the keyboard"
  for selector in got["hover"]:
    assert selector.startswith(':root[data-keyboard-nav="true"]'), selector
