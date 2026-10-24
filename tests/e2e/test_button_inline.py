"""Clean & Push ends the checkbox row and wraps under it when the row is narrow.

The options card has no foot. The run button sits at the right end of the
last checkbox line when that line leaves room. When it does not, it drops
under the boxes, right-aligned. Its height stays the 34 px of every control
(docs/design.md).
"""

from __future__ import annotations

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

CARD = ".repo-card:has-text('shop-web') .repo-name"
CONTROL_HEIGHT = 34
GAP = 8
ROW = """() => {
  const r = (e) => e.getBoundingClientRect();
  const row = document.querySelector('#checks');
  const style = getComputedStyle(row);
  const boxes = [...row.querySelectorAll('.check')].map((e) => r(e));
  const lastTop = Math.max(...boxes.map((b) => b.top));
  const lastLine = boxes.filter((b) => b.top === lastTop);
  const start = r(document.querySelector('#start'));
  return {
    rowRight: r(row).right - parseFloat(style.paddingRight),
    rowWidth: row.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight),
    lastLineWidth: lastLine.reduce((n, b) => n + b.width, 0) + 20 * (lastLine.length - 1),
    lastTop,
    boxBottom: Math.max(...boxes.map((b) => b.bottom)),
    start: { top: start.top, right: start.right, height: start.height, width: start.width },
  };
}"""


@pytest.mark.parametrize(
  ("width", "expected"), [(1920, "beside"), (1360, None), (660, "under")]
)
def test_the_button_ends_the_last_checkbox_line_or_drops_under_it(
  desktop: Walker, width: int, expected: str | None
) -> None:
  page = desktop.page
  size = page.viewport_size
  page.set_viewport_size({"width": width, "height": 900})
  try:
    desktop.goto(1200)
    desktop.click(CARD, 800)
    assert (
      page.eval_on_selector_all("#options-card .card-foot", "els => els.length") == 0
    )
    assert page.eval_on_selector("#checks #start", "e => e.tagName") == "BUTTON"
    row = page.evaluate(ROW)
    fits = row["lastLineWidth"] + GAP + row["start"]["width"] <= row["rowWidth"]
    placement = "beside" if fits else "under"
    assert expected in (None, placement), row
    # right-aligned at every width, at the control height
    assert row["start"]["right"] == pytest.approx(row["rowRight"], abs=0.5), row
    assert row["start"]["height"] == CONTROL_HEIGHT
    if fits:
      assert row["start"]["top"] == pytest.approx(row["lastTop"], abs=0.5), row
    else:
      assert row["start"]["top"] >= row["boxBottom"], row
  finally:
    page.set_viewport_size(size)
