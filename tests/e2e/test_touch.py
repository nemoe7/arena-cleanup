"""Touch targets on a phone: the pill and the repo name hit 44 px tall (docs/design.md)."""

from __future__ import annotations

import pytest

from .conftest import Walker

pytestmark = pytest.mark.e2e

TOUCH_PX = 44
HIT = """
(selector) => {
  const node = document.querySelector(selector);
  const box = node.getBoundingClientRect();
  const x = box.left + box.width / 2;
  const owns = (hit) => hit === node || node.contains(hit);
  return {
    height: box.height,
    above: owns(document.elementFromPoint(x, box.top - 8)),
    below: owns(document.elementFromPoint(x, box.bottom + 8)),
  };
}
"""
INPUT_HEIGHT = (
  "() => document.querySelector('.chip-edit input').getBoundingClientRect().height"
)


@pytest.mark.parametrize("selector", ["button.pill", ".repo-name"])
def test_phone_hit_box_reaches_44_px_around_the_same_glyphs(
  phone: Walker, selector: str
) -> None:
  phone.goto()
  hit = phone.page.evaluate(HIT, selector)
  assert hit["height"] < TOUCH_PX
  assert hit["above"] and hit["below"]


@pytest.mark.parametrize("selector", ["button.pill", ".repo-name"])
def test_desktop_keeps_the_visual_hit_box(desktop: Walker, selector: str) -> None:
  desktop.goto()
  hit = desktop.page.evaluate(HIT, selector)
  assert not hit["above"] and not hit["below"]


def test_phone_claim_inputs_are_44_px_tall(phone: Walker) -> None:
  phone.goto()
  phone.click("#settings-btn")
  assert phone.page.evaluate(INPUT_HEIGHT) >= TOUCH_PX
