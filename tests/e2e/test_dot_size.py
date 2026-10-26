"""The live dot in a pill or a button is 8 px, the nuu default.

The header tool dots keep the 6 px small size. The busy face of the twin
button narrows its glyph box to the dot, so the pair centres (docs/design.md).
"""

from __future__ import annotations

import pytest

from scripts.walk import Walker
from tests.e2e.test_done_button import open_repo

pytestmark = pytest.mark.e2e

DOT = 8
BOXES = """() => {
  // layout sizes: the pulse scales a live dot, which a client rect would show
  const box = (node) => [node.offsetWidth, node.offsetHeight];
  return {
    dots: [...document.querySelectorAll('.pill .dot, .arena-item .dot')].map(box),
    tool: box(document.querySelector('.env-dots i')),
  };
}"""
BUSY = "() => document.querySelector('.repo-card .btn.twin .busy .ico-svg').offsetWidth"


def test_every_pill_dot_is_the_nuu_size_and_the_busy_glyph_box_matches(
  desktop: Walker,
) -> None:
  desktop.goto()
  busy = desktop.page.evaluate(BUSY)
  open_repo(desktop, "data-pipeline")
  desktop.page.wait_for_selector(".arena-item .dot.live")
  boxes = desktop.page.evaluate(BOXES)
  assert boxes["dots"], "the repo view shows a live dot in an arena row"
  assert all(size == [DOT, DOT] for size in boxes["dots"])
  assert boxes["tool"][0] < DOT, "the header tool dots stay the small size"
  assert busy == DOT, "the busy glyph box of a card button is the dot's width"
