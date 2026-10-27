"""The ahead chip pads arrow ink and count alike, and trails the PR pill.

The arrow glyph keeps blank space inside its icon box. An equal box padding
reads as a wider gap on the arrow side. The chip pulls the icon in and narrows
the gap by the same amount. The ink sits 8 px from the edge and from the count.

The chip hides at zero. It sits after the PR pill, so its exit moves nothing.
"""

from __future__ import annotations

import pytest

from scripts.walk import Walker
from tests.e2e.test_done_button import FETCH, LIST, ONE, zero_ahead

pytestmark = pytest.mark.e2e

CARD = ".repo-card:has-text('shop-web')"
TAIL = f"{CARD} .arena-row .arena-tail"
PILL = f"{TAIL} > :not(.ahead)"
ORDER = """(tail) => {
  const kids = [...tail.children].map((k) => k.className);
  return { first: kids[0], last: kids[kids.length - 1], count: kids.length };
}"""

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
  walker.goto()
  walker.page.wait_for_selector(".pill.ahead")
  ink = walker.page.evaluate(INK)
  assert abs(ink["arrowLeft"] - ink["countRight"]) <= 1.5, ink
  assert abs(ink["gap"] - ink["countRight"]) <= 1.5, ink


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_the_pill_leads_and_keeps_its_place_without_the_chip(
  request: pytest.FixtureRequest, width: str
) -> None:
  walker: Walker = request.getfixturevalue(width)
  page = walker.page
  walker.goto()
  page.wait_for_selector(f"{TAIL} .ahead")
  order = page.eval_on_selector(TAIL, ORDER)
  assert order["count"] == 2, order
  assert "ahead" not in order["first"], order
  assert "ahead" in order["last"], order
  left = page.eval_on_selector(PILL, "e => e.getBoundingClientRect().left")
  for pattern in (LIST, FETCH, ONE):
    page.route(pattern, zero_ahead)
  try:
    walker.goto()
    page.wait_for_selector(f"{TAIL} .ahead", state="detached")
    still = page.eval_on_selector(PILL, "e => e.getBoundingClientRect().left")
  finally:
    page.unroute_all(behavior="ignoreErrors")
  assert abs(still - left) <= 0.5, (left, still)
