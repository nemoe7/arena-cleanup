"""Every select draws its caret with the chevron-down glyph, inside its right padding.

The glyph sits in the `select-wrap` span beside the select, sized from the
icon ladder, and takes no pointer events. No select paints a CSS gradient
caret any more (docs/design.md).
"""

from __future__ import annotations

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

CARD = ".repo-card:has-text('shop-web') .repo-name"
CHEVRON = "m6 9 6 6 6-6"
BOX = "(e) => e.getBoundingClientRect().toJSON()"
PAINT = (
  "(s) => ({ image: getComputedStyle(s).backgroundImage,"
  " look: getComputedStyle(s).appearance,"
  " pad: parseFloat(getComputedStyle(s).paddingRight) })"
)
GLYPH = (
  "(g) => ({ events: getComputedStyle(g).pointerEvents,"
  " path: g.querySelector('svg path').getAttribute('d'),"
  " hidden: g.getAttribute('aria-hidden') })"
)


def caret_sits_in_the_padding(walker: Walker, select_id: str) -> None:
  page = walker.page
  wrap = f"#{select_id}"
  assert (
    page.eval_on_selector(wrap, "(s) => s.parentElement.className") == "select-wrap"
  )
  paint = page.eval_on_selector(wrap, PAINT)
  assert paint["image"] == "none"
  assert paint["look"] == "none"
  glyph = page.eval_on_selector(f"{wrap} + .ico-svg", GLYPH)
  assert glyph == {"events": "none", "path": CHEVRON, "hidden": "true"}
  select = page.eval_on_selector(wrap, BOX)
  icon = page.eval_on_selector(f"{wrap} + .ico-svg", BOX)
  assert icon["width"] == 14 and icon["height"] == 14
  assert (
    select["right"] - paint["pad"] <= icon["left"] < icon["right"] < select["right"]
  )
  centre = select["top"] + select["height"] / 2
  assert abs(icon["top"] + icon["height"] / 2 - centre) < 1


def test_the_sort_select_carries_the_chevron(desktop: Walker) -> None:
  desktop.goto()
  caret_sits_in_the_padding(desktop, "repo-sort")


def test_the_target_select_carries_the_chevron(desktop: Walker) -> None:
  desktop.goto()
  desktop.click(CARD)
  desktop.page.wait_for_selector("#branch option", state="attached")
  caret_sits_in_the_padding(desktop, "branch")


def test_the_sort_select_fills_the_phone_bar_with_its_chevron(phone: Walker) -> None:
  phone.goto()
  caret_sits_in_the_padding(phone, "repo-sort")
  select = phone.page.eval_on_selector("#repo-sort", BOX)
  tools = phone.page.eval_on_selector(".hero-tools", BOX)
  reload = phone.page.eval_on_selector("#repos-refresh", BOX)
  assert select["left"] == tools["left"]
  assert select["right"] < reload["left"] <= select["right"] + 12
  assert select["height"] == 44
