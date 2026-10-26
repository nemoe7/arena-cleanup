"""The arena row: one line in a dashboard row, two lines on a card, no dots (docs/design.md)."""

from __future__ import annotations

import pytest

from scripts import demo
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


def test_the_desktop_row_puts_the_pills_beside_the_name(desktop: Walker) -> None:
  desktop.goto()
  name_top, tail_top, name_left, tail_left = row_geometry(desktop)
  assert abs(tail_top - name_top) < 8, "one line"
  assert tail_left > name_left
  assert desktop.count(f"{CARD} .arena-row .dot") == 0
  assert desktop.count(f"{CARD} .arena-tail .pill") >= 2
  # infra-tools shares the arena history with shop-web, and its main moved on
  # by MAIN_LATER: the chip shows the net count
  shop = int(desktop.text(f"{CARD} .ahead .n"))
  infra = int(desktop.text(".repo-card:has-text('infra-tools') .ahead .n"))
  assert shop >= 1
  assert infra == shop - len(demo.MAIN_LATER)


def test_the_phone_card_row_keeps_the_two_lines(phone: Walker) -> None:
  phone.goto()
  name_top, tail_top, name_left, tail_left = row_geometry(phone)
  assert tail_top > name_top
  assert tail_left == name_left
  assert phone.count(f"{CARD} .arena-row .dot") == 0


def test_the_repo_name_is_the_control_that_opens_the_repo(desktop: Walker) -> None:
  desktop.goto()
  assert desktop.count(".repo-card[role]") == 0
  assert desktop.count(".repo-card button.repo-name") == desktop.count(".repo-card")
  desktop.page.focus(f"{CARD} .repo-name")
  desktop.page.keyboard.press("Enter")
  desktop.page.wait_for_selector("#view-repo:not([hidden])")
  assert desktop.text("#repo-title").strip() == "shop-web"
