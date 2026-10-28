"""An arena row tint spans its name, checks button, and trash button.

Each sidebar arena branch is one row: a select button with its name and two
square icon buttons. Hover and selected tints sit on the row box. They end at
the trash button, not at the name (docs/design.md).
"""

from __future__ import annotations

import pytest

from tests.e2e.harness import Walker

pytestmark = pytest.mark.e2e

BRANCH = "arena/5e1f7d2c-data-pipeline"
OTHER = "arena/6d8b3a4e-data-pipeline"
ROW = f".arena-item:has(.row-btn[data-branch='{BRANCH}'])"
OTHER_ROW = f".arena-item:has(.row-btn[data-branch='{OTHER}'])"
CARD = ".repo-card:has-text('data-pipeline') .repo-name"
CLEAR = {"rgba(0, 0, 0, 0)", "transparent"}
BG = "e => getComputedStyle(e).backgroundColor"
RIGHT = "e => e.getBoundingClientRect().right"
SELECTED = "e => e.classList.contains('selected')"
# true once the element's own surface is clear, or tinted, as `want` says
SURFACE = """([e, clear, want]) => {
  return clear.includes(getComputedStyle(e).backgroundColor) === want;
}"""


def open_repo(walker: Walker) -> None:
  walker.goto()
  walker.click(CARD)
  walker.page.wait_for_selector(OTHER_ROW)


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_the_selected_tint_ends_at_the_trash_button(
  request: pytest.FixtureRequest, width: str
) -> None:
  walker: Walker = request.getfixturevalue(width)
  open_repo(walker)
  page = walker.page
  # two branches: the page opens on one, a click moves the mark to this row
  assert page.eval_on_selector(ROW, SELECTED) is False
  assert page.eval_on_selector(OTHER_ROW, SELECTED) is True
  walker.click(f"{ROW} .row-btn")
  assert page.eval_on_selector(ROW, SELECTED) is True
  assert page.eval_on_selector(OTHER_ROW, SELECTED) is False
  assert (
    page.eval_on_selector(f"{ROW} .row-btn", "e => e.getAttribute('aria-pressed')")
    == "true"
  )
  # the row carries the tint. Its name button stays clear inside it
  assert page.eval_on_selector(ROW, BG) not in CLEAR
  assert page.eval_on_selector(f"{ROW} .row-btn", BG) in CLEAR
  # the tinted box reaches past its name to its trash button
  name_right = page.eval_on_selector(f"{ROW} .row-btn", RIGHT)
  trash_right = page.eval_on_selector(f"{ROW} .arena-del", RIGHT)
  row_right = page.eval_on_selector(ROW, RIGHT)
  assert name_right < trash_right <= row_right


def test_the_hover_tint_covers_the_row_under_a_pointer(desktop: Walker) -> None:
  open_repo(desktop)
  page = desktop.page
  # a click leaves its pointer over this row list, so park it top left
  page.mouse.move(0, 0)
  row = page.query_selector(ROW)
  page.wait_for_function(SURFACE, arg=[row, sorted(CLEAR), True])
  assert page.eval_on_selector(ROW, SELECTED) is False
  page.hover(f"{ROW} .arena-del")
  page.wait_for_function(SURFACE, arg=[row, sorted(CLEAR), False])
  # the icon button keeps its own ring on top of the row tint
  assert page.eval_on_selector(f"{ROW} .arena-del", BG) not in CLEAR
