"""The options card: phone tap targets and the arena branch labels."""

from __future__ import annotations

from scripts.walk import Walker

TAP_TARGET_PX = 44
FIELD_TEXT_PX = 16.0
BOX = "e => { const b = e.getBoundingClientRect(); return [b.width, b.height]; }"


def test_the_path_field_and_browse_are_tap_targets(phone: Walker) -> None:
  phone.goto(400)
  phone.click(".repo-card", 800)
  width, height = phone.page.eval_on_selector("#pathin", BOX)
  assert height >= TAP_TARGET_PX
  assert width > TAP_TARGET_PX
  size = phone.page.eval_on_selector(
    "#pathin", "e => parseFloat(getComputedStyle(e).fontSize)"
  )
  assert size == FIELD_TEXT_PX
  width, height = phone.page.eval_on_selector("#browse", BOX)
  assert min(width, height) >= TAP_TARGET_PX
