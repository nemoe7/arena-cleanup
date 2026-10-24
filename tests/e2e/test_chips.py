"""The ahead chip pads arrow ink and count alike.

The arrow glyph keeps blank space inside its icon box. An equal box padding
reads as a wider gap on the arrow side. The chip pulls the icon in and narrows
the gap by the same amount. The ink sits 8 px from the edge and from the count.
"""

from __future__ import annotations

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

INK = """() => {
  const pill = document.querySelector('.pill.ahead');
  const box = pill.getBoundingClientRect();
  const paths = [...pill.querySelectorAll('svg path, svg line, svg polyline')];
  const ink = paths.map((p) => p.getBoundingClientRect());
  const left = Math.min(...ink.map((r) => r.left));
  const right = Math.max(...ink.map((r) => r.right));
  const n = pill.querySelector('.n').getBoundingClientRect();
  return { arrowLeft: left - box.left, gap: n.left - right, countRight: box.right - n.right };
}"""


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_the_arrow_ink_and_the_count_share_one_inset(
  request: pytest.FixtureRequest, width: str
) -> None:
  walker: Walker = request.getfixturevalue(width)
  walker.goto(1200)
  walker.page.wait_for_selector(".pill.ahead")
  ink = walker.page.evaluate(INK)
  assert abs(ink["arrowLeft"] - ink["countRight"]) <= 1.5, ink
  assert abs(ink["gap"] - ink["countRight"]) <= 1.5, ink
