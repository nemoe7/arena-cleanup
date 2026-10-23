"""The arena row on a repo card: two lines at every width, no dots (docs/design.md)."""

from __future__ import annotations

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

CARD = ".repo-card:has-text('shop-web')"
TOP = "e => e.getBoundingClientRect().top"
LEFT = "e => e.getBoundingClientRect().left"


def row_geometry(walker: Walker) -> tuple[float, float, float, float]:
  page = walker.page
  page.wait_for_selector(f"{CARD} .arena-row .arena-tail .pill")
  name_top = page.eval_on_selector(f"{CARD} .arena-row .bname", TOP)
  tail_top = page.eval_on_selector(f"{CARD} .arena-row .arena-tail", TOP)
  name_left = page.eval_on_selector(f"{CARD} .arena-row .bname", LEFT)
  tail_left = page.eval_on_selector(f"{CARD} .arena-row .arena-tail", LEFT)
  return name_top, tail_top, name_left, tail_left


def test_the_desktop_card_row_puts_the_pills_under_the_name(desktop: Walker) -> None:
  desktop.goto(1200)
  name_top, tail_top, name_left, tail_left = row_geometry(desktop)
  assert tail_top > name_top
  assert tail_left == name_left
  assert desktop.count(f"{CARD} .arena-row .dot") == 0
  assert desktop.count(f"{CARD} .arena-tail .pill") >= 2


def test_the_phone_card_row_keeps_the_two_lines(phone: Walker) -> None:
  phone.goto(1200)
  name_top, tail_top, name_left, tail_left = row_geometry(phone)
  assert tail_top > name_top
  assert tail_left == name_left
  assert phone.count(f"{CARD} .arena-row .dot") == 0
