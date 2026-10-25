"""The close x of a dialog head rests bare and shows its surface on hover and press.

At rest it has no fill and no border, unlike the other icon buttons. Under a
pointer, and while pressed, it paints `--surface-3` with the `--line-2`
border (docs/design.md).
"""

from __future__ import annotations

import pytest

from scripts.walk import Walker
from tests.e2e.test_checks_inline import BILLING, close_modal, open_modal

pytestmark = pytest.mark.e2e

CLOSE = "#checks-modal .modal-head .icon-btn"
CLEAR = "rgba(0, 0, 0, 0)"
FACE = """(sel) => {
  const el = document.querySelector(sel);
  const css = getComputedStyle(el);
  const token = (name) => {
    const probe = document.createElement('span');
    probe.style.color = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    document.body.append(probe);
    const value = getComputedStyle(probe).color;
    probe.remove();
    return value;
  };
  return { fill: css.backgroundColor, line: css.borderTopColor,
    surface: token('--surface-3'), rule: token('--line-2') };
}"""


def test_the_close_x_rests_bare_and_fills_under_a_pointer(desktop: Walker) -> None:
  page = desktop.page
  open_modal(desktop, BILLING)
  try:
    rest = page.evaluate(FACE, CLOSE)
    assert rest["fill"] == CLEAR and rest["line"] == CLEAR, (
      "no idle fill, no idle border"
    )
    refresh = page.evaluate(FACE, "#repos-refresh")
    assert refresh["fill"] != CLEAR, "the other icon buttons keep their fill"
    page.hover(CLOSE)
    page.wait_for_function(
      f"() => getComputedStyle(document.querySelector('{CLOSE}')).backgroundColor !== '{CLEAR}'"
    )
    hover = page.evaluate(FACE, CLOSE)
    assert hover["fill"] == hover["surface"] and hover["line"] == hover["rule"]
    page.mouse.down()
    pressed = page.evaluate(FACE, CLOSE)
    page.mouse.up()
    assert pressed["fill"] == pressed["surface"] and pressed["line"] == pressed["rule"]
  finally:
    if page.evaluate("document.getElementById('checks-modal').open"):
      close_modal(desktop)
