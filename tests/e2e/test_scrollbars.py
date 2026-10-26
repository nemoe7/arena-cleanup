"""Scrollbars follow the nuu recipe, and only the scrolling views reserve a gutter.

Chromium knows `::-webkit-scrollbar`, so the standard `scrollbar-width` stays
`auto` there and the drawn 10 px thumb shows. The page root reserves no
gutter, since on a desktop the views scroll and the page never does. So a
view spans the whole window (docs/design.md).
"""

from __future__ import annotations

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

GUTTERS = """() => ({
  root: getComputedStyle(document.documentElement).scrollbarGutter,
  view: getComputedStyle(document.getElementById('view-dashboard')).scrollbarGutter,
  width: getComputedStyle(document.getElementById('view-dashboard')).scrollbarWidth,
  viewW: document.getElementById('view-dashboard').offsetWidth,
  windowW: innerWidth,
})"""


def test_the_root_reserves_no_gutter_and_chromium_keeps_the_drawn_thumb(
  desktop: Walker,
) -> None:
  desktop.goto()
  got = desktop.page.evaluate(GUTTERS)
  assert got["root"] == "auto", "the page root reserves no gutter"
  assert got["view"] == "stable", "a scrolling view keeps its gutter"
  assert got["width"] == "auto", "the standard width stays off where WebKit draws"
  assert got["viewW"] == got["windowW"], "the view spans the whole window"
