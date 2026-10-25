"""Deleting an arena branch from the repo view: a modal first, then one request."""

from __future__ import annotations

import json
from typing import Any

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

BRANCH = "arena/3f7c2e1a-shop-web"
ROW = f".arena-item:has(.row-btn[data-branch='{BRANCH}'])"
OPEN = "() => document.querySelector('#confirm-delete').open"
BOX = "e => { const b = e.getBoundingClientRect(); return [b.width, b.height]; }"
CANCEL = "#confirm-delete .modal-actions button[value='cancel']"


def test_the_modal_asks_before_the_branch_goes(desktop: Walker) -> None:
  page = desktop.page
  bodies: list[dict[str, Any]] = []

  def fake(route: Any) -> None:
    bodies.append(json.loads(route.request.post_data or "{}"))
    route.fulfill(
      status=200,
      content_type="application/json",
      body=json.dumps({"deleted": BRANCH, "status": {}}),
    )

  page.route("**/api/repos/*/arena/delete", fake)
  desktop.goto(1200)
  desktop.click(".repo-card:has-text('shop-web') .repo-name", 800)
  assert desktop.count(f"{ROW} .arena-del") == 1
  # Cancel: the modal closes and the page sends nothing
  desktop.click(f"{ROW} .arena-del", 300)
  assert page.evaluate(OPEN) is True
  assert desktop.text("#confirm-branch") == BRANCH
  desktop.click(CANCEL, 300)
  assert page.evaluate(OPEN) is False
  assert bodies == []
  # the x top right closes it the same way, and it is a square icon button
  desktop.click(f"{ROW} .arena-del", 300)
  box = page.eval_on_selector("#confirm-x", BOX)
  assert box[0] == box[1] == 32
  desktop.click("#confirm-x", 300)
  assert page.evaluate(OPEN) is False
  assert bodies == []
  # Escape closes it too
  desktop.click(f"{ROW} .arena-del", 300)
  page.keyboard.press("Escape")
  page.wait_for_timeout(200)
  assert page.evaluate(OPEN) is False
  assert bodies == []
  # Delete: one request that names the branch
  desktop.click(f"{ROW} .arena-del", 300)
  desktop.click("#confirm-go", 600)
  assert page.evaluate(OPEN) is False
  assert bodies == [{"branch": BRANCH}]
  page.unroute("**/api/repos/*/arena/delete")


def test_the_phone_keeps_the_control_a_thumb_can_hit(phone: Walker) -> None:
  phone.goto(1200)
  phone.click(".repo-card:has-text('shop-web') .repo-name", 800)
  box = phone.page.eval_on_selector(f"{ROW} .arena-del", BOX)
  assert box[0] >= 44 and box[1] >= 44
  phone.click(f"{ROW} .arena-del", 300)
  assert phone.page.eval_on_selector("#confirm-x", BOX) == [44, 44]
  phone.click("#confirm-x", 300)
  assert phone.page.evaluate(OPEN) is False
