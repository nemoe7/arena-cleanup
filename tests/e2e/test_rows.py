"""Dashboard rows: above 1200 a repo is one full-width row, at 1200 and below it is a card."""

from __future__ import annotations

from typing import Any

import pytest

from scripts.walk import Demo, Walker

pytestmark = pytest.mark.e2e

CARD = ".repo-card:has-text('data-pipeline')"
PROBE = """(card) => {
  const box = (e) => {
    const r = e.getBoundingClientRect();
    return { top: Math.round(r.top), left: Math.round(r.left), right: Math.round(r.right), width: r.width };
  };
  const mid = (e) => {
    const r = e.getBoundingClientRect();
    return { x: Math.round(r.left), y: Math.round(r.top + r.height / 2) };
  };
  const rows = [...card.querySelectorAll('.arena-row')].map(box);
  const grid = getComputedStyle(card.parentElement).gridTemplateColumns.split(' ').length;
  return {
    grid,
    width: box(card).width,
    gridWidth: box(card.parentElement).width,
    rowTops: rows.map((r) => r.top),
    rowLefts: rows.map((r) => r.left),
    bname: mid(card.querySelector('.arena-row .bname')),
    tail: mid(card.querySelector('.arena-row .arena-tail')),
    icoLeft: box(card.querySelector('.repo-ico')).left,
    nameLeft: box(card.querySelector('.repo-name')).left,
    nameRight: box(card.querySelector('.repo-name')).right,
    arenaLeft: box(card.querySelector('.arena-list')).left,
    actionsLeft: box(card.querySelector('.card-actions')).left,
    actionsRight: box(card.querySelector('.card-actions')).right,
    removeLeft: box(card.querySelector('.rm')).left,
    removeRight: box(card.querySelector('.rm')).right,
    arenaRight: box(card.querySelector('.arena-list')).right,
    removeTop: box(card.querySelector('.rm')).top,
    icoTop: box(card.querySelector('.repo-ico')).top,
    cardRight: box(card).right,
  };
}"""


def probe(browser: Any, demo: Demo, width: int) -> dict[str, Any]:
  context = browser.new_context(viewport={"width": width, "height": 900})
  try:
    walker = Walker(context, demo.url)
    walker.goto(600)
    walker.page.wait_for_selector(f"{CARD} .arena-row .arena-tail .pill")
    return walker.page.eval_on_selector(CARD, PROBE)
  finally:
    context.close()


def test_above_1200_a_repo_is_one_row(browser: Any, demo: Demo) -> None:
  row = probe(browser, demo, 1201)
  assert row["grid"] == 6, "one column per cell, shared by every row"
  assert row["width"] == row["gridWidth"], "a full-width row"
  assert len(row["rowTops"]) == 2
  assert row["rowTops"][0] < row["rowTops"][1], "arena rows stacked"
  assert row["rowLefts"][0] == row["rowLefts"][1]
  assert row["bname"]["y"] == row["tail"]["y"], "one line: the name, then the pills"
  assert row["bname"]["x"] < row["tail"]["x"]
  # left to right: the name, the arena rows, the button, then remove
  assert row["nameRight"] < row["arenaLeft"] < row["actionsLeft"] < row["removeLeft"]
  assert row["removeLeft"] - row["actionsRight"] <= 12
  # spread: the arena area takes the free width, Remove ends at the padding
  assert row["actionsLeft"] - row["arenaRight"] <= 12
  assert row["cardRight"] - row["removeRight"] <= 17


def test_at_1200_the_repos_are_cards(browser: Any, demo: Demo) -> None:
  card = probe(browser, demo, 1200)
  assert card["grid"] > 1
  assert card["width"] < card["gridWidth"] / 2
  assert card["rowTops"][0] < card["rowTops"][1], "arena rows stacked"
  assert card["rowLefts"][0] == card["rowLefts"][1]
  assert card["bname"]["y"] < card["tail"]["y"], "two lines: the name over the pills"
  # one left edge: the icon, the arena rows, and the button. The name follows the icon
  assert card["icoLeft"] == card["rowLefts"][0] == card["actionsLeft"]
  assert card["icoLeft"] < card["nameLeft"] < card["removeLeft"]
  assert card["removeTop"] == card["icoTop"], "remove sits top right"
