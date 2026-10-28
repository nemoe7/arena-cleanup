"""The focus ring follows the keyboard.

A focus that no key moved draws no ring, as the nuu house rule asks. Tab or an
arrow key sets `data-keyboard-nav` on the root, and the ring shows on the active
control. A pointer press clears the flag again (docs/design.md).
"""

from __future__ import annotations

import pytest

from tests.e2e.harness import Walker

pytestmark = pytest.mark.e2e

FLAG = "() => document.documentElement.dataset.keyboardNav || null"
ACTIVE = """() => {
  const s = getComputedStyle(document.activeElement);
  return [document.activeElement.id, s.outlineStyle, s.outlineWidth];
}"""
SCRIPT_FOCUS = """() => {
  const b = document.querySelector('#settings-btn');
  b.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
  b.focus();
  return getComputedStyle(b).outlineStyle;
}"""


def test_the_ring_follows_the_keyboard(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto()
  assert page.evaluate(FLAG) is None, "a fresh page carries no flag"
  assert page.evaluate(SCRIPT_FOCUS) == "none", "a pointer focus draws no ring"
  page.keyboard.press("Tab")
  assert page.evaluate(FLAG) == "true", "Tab sets the flag"
  # under reduced motion the outline change is a transition of .01 ms: let it end
  desktop.settle()
  active, style, width = page.evaluate(ACTIVE)
  assert active, "Tab moved the focus"
  assert (style, width) == ("solid", "2px"), "the active control wears the ring"
  page.dispatch_event("#main", "pointerdown")
  assert page.evaluate(FLAG) is None, "a pointer press clears the flag"
  page.keyboard.press("ArrowDown")
  assert page.evaluate(FLAG) == "true", "an arrow key sets it again"
