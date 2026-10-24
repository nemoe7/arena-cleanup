"""Dashboard rows: above 1200 the repos are one table element, at 1200 and below they are cards."""

from __future__ import annotations

import json
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
  const lines = (e) => {
    const range = document.createRange();
    range.selectNodeContents(e);
    return range.getClientRects().length;
  };
  const rows = [...card.querySelectorAll('.arena-row')].map(box);
  const table = card.closest('table');
  const ths = [...table.querySelectorAll('thead th')];
  const style = getComputedStyle(card);
  const pad = (s) => getComputedStyle(card.querySelector(s)).padding;
  return {
    tag: card.tagName,
    cells: card.children.length,
    display: style.display,
    bodyColumns: getComputedStyle(card.parentElement).gridTemplateColumns.split(' ').length,
    width: box(card).width,
    gridWidth: box(table).width,
    gridInner: box(table).width - 2 * parseFloat(getComputedStyle(table).borderLeftWidth),
    gridBorder: getComputedStyle(table).borderTopWidth,
    headShown: getComputedStyle(table.tHead).display !== 'none',
    headLabels: ths.map((e) => e.textContent),
    headScopes: ths.map((e) => e.getAttribute('scope')),
    headLefts: ths.map((e) => box(e).left + 12),
    rule: [getComputedStyle(card.firstElementChild).borderTopWidth, style.borderLeftWidth, style.borderRadius],
    pads: [pad('.repo-head > div'), pad('.repo-meta'), pad('.arena-list'), pad('.card-actions')],
    branchLeft: box(card.querySelector('.repo-meta .pill')).left,
    cleanLeft: box(card.querySelector('.card-actions .btn')).left,
    bnameLeft: box(card.querySelector('.arena-row .bname')).left,
    rowTops: rows.map((r) => r.top),
    rowLefts: rows.map((r) => r.left),
    bname: mid(card.querySelector('.arena-row .bname')),
    tail: mid(card.querySelector('.arena-row .arena-tail')),
    icoLeft: box(card.querySelector('.repo-ico')).left,
    nameLeft: box(card.querySelector('.repo-name')).left,
    nameRight: box(card.querySelector('.repo-name')).right,
    nameLines: lines(card.querySelector('.repo-name')),
    arenaLeft: box(card.querySelector('.arena-list')).left,
    actionsLeft: box(card.querySelector('.card-actions')).left,
    actionsRight: box(card.querySelector('.card-actions')).right,
    removeLeft: box(card.querySelector('.rm')).left,
    removeRight: box(card.querySelector('.rm')).right,
    arenaRight: box(card.querySelector('.arena-list')).right,
    removeTop: box(card.querySelector('.rm')).top,
    icoTop: box(card.querySelector('.repo-ico')).top,
    headMids: ['.repo-ico', '.repo-name', '.rm'].map((s) => mid(card.querySelector(s)).y),
    cardRight: box(card).right,
  };
}"""


LONG_BRANCH = "arena/" + "session-with-a-very-long-name-" * 12
MODE = "e => getComputedStyle(e).display"
TABLE = "document.getElementById('repo-table')"


def lengthen(route: Any) -> None:
  """The first arena branch of the probed repo gets a name wider than any window."""
  reply = route.fetch()
  repos = reply.json()
  for repo in repos:
    status = repo.get("status") or {}
    if repo["name"] != "data-pipeline" or not status.get("arena"):
      continue
    old = status["arena"][0]
    status["arena"][0] = LONG_BRANCH
    for field in ("ahead", "pr", "tips"):
      if old in status.get(field, {}):
        status[field][LONG_BRANCH] = status[field][old]
  route.fulfill(response=reply, body=json.dumps(repos))


def probe(
  browser: Any, demo: Demo, width: int, long_branch: bool = False
) -> dict[str, Any]:
  context = browser.new_context(viewport={"width": width, "height": 900})
  try:
    walker = Walker(context, demo.url)
    if long_branch:
      walker.page.route("**/api/fetch", lengthen)
      walker.page.route("**/api/repos", lengthen)
    walker.goto(600)
    walker.page.wait_for_selector(f"{CARD} .arena-row .arena-tail .pill")
    return walker.page.eval_on_selector(CARD, PROBE)
  finally:
    context.close()


def test_above_1200_a_repo_is_one_table_row(browser: Any, demo: Demo) -> None:
  row = probe(browser, demo, 1201)
  assert (row["tag"], row["display"], row["cells"]) == ("TR", "table-row", 4)
  assert row["width"] == row["gridInner"], "a full-width row inside the table frame"
  assert row["gridBorder"] == "1px", "one frame around the table"
  # a header row names each column, and its labels start where cell content does
  assert row["headShown"]
  assert row["headLabels"] == ["Repo", "Default", "Arena Branches", "Actions"]
  assert row["headScopes"] == ["col"] * 4
  assert row["headLefts"] == [
    row["icoLeft"],
    row["branchLeft"],
    row["bnameLeft"],
    row["cleanLeft"],
  ]
  # 1 px rules split the rows, no card border or radius, and 12 px cells
  assert row["rule"] == ["1px", "0px", "0px"]
  assert row["pads"] == ["12px"] * 4
  assert len(row["rowTops"]) == 2
  assert row["rowTops"][0] < row["rowTops"][1], "arena rows stacked"
  assert row["rowLefts"][0] == row["rowLefts"][1]
  assert row["bname"]["y"] == row["tail"]["y"], "one line: the name, then the pills"
  assert row["bname"]["x"] < row["tail"]["x"]
  # left to right: name, arena rows, the button, then remove
  assert row["nameLines"] == 1, "the name stays on one line in its column"
  assert row["nameRight"] < row["arenaLeft"] < row["actionsLeft"] < row["removeLeft"]
  assert row["removeLeft"] - row["actionsRight"] <= 12
  # spread: the arena area takes all free width, Remove ends at the padding
  assert row["actionsLeft"] - row["arenaRight"] <= 12
  assert row["cardRight"] - row["removeRight"] <= 17


def test_a_hovered_table_row_tints(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto(600)
  page.wait_for_selector(f"{CARD} .arena-row .arena-tail .pill")
  page.mouse.move(0, 0)
  page.wait_for_timeout(200)
  bg = "e => getComputedStyle(e).backgroundColor"
  clear = {"rgba(0, 0, 0, 0)", "transparent"}
  assert page.eval_on_selector(CARD, bg) in clear, "a resting row has no own surface"
  page.hover(f"{CARD} .bname")
  page.wait_for_timeout(200)
  assert page.eval_on_selector(CARD, bg) not in clear, "the pointer tints the row"


def test_the_rows_fold_into_cards_when_the_table_outgrows_its_room(
  browser: Any, demo: Demo
) -> None:
  # the demo table fits a 1200 px window, so it stays a table there
  row = probe(browser, demo, 1200)
  assert (row["tag"], row["display"]) == ("TR", "table-row")
  # a branch name wider than the window pushes the natural table past its room
  card = probe(browser, demo, 1200, long_branch=True)
  assert card["display"] == "grid", "the row is the card"
  assert card["bodyColumns"] > 1, "the body is the card grid"
  assert card["width"] < card["gridWidth"] / 2
  assert not card["headShown"], "no header row over cards"
  assert card["gridBorder"] == "0px" and card["rule"][2] == "12px", "a card, not a row"
  assert card["rowTops"][0] < card["rowTops"][1], "arena rows stacked"
  assert card["rowLefts"][0] == card["rowLefts"][1]
  assert card["bname"]["y"] < card["tail"]["y"], "two lines: the name over the pills"
  # one left edge: icon and arena rows. The button sits bottom right
  assert card["icoLeft"] == card["rowLefts"][0]
  assert card["cardRight"] - card["actionsRight"] <= 17
  assert card["actionsLeft"] > card["nameLeft"]
  assert card["icoLeft"] < card["nameLeft"] < card["removeLeft"]
  assert card["removeTop"] <= card["icoTop"], "remove sits top right"
  assert max(card["headMids"]) - min(card["headMids"]) <= 1, "one centre line on top"
  phone = probe(browser, demo, 360)
  assert phone["display"] == "grid" and phone["bodyColumns"] == 1, "one column"
  assert max(phone["headMids"]) - min(phone["headMids"]) <= 1, (
    "44 px remove, same centre"
  )


def test_a_resized_window_folds_and_unfolds_the_rows(browser: Any, demo: Demo) -> None:
  context = browser.new_context(viewport={"width": 1400, "height": 900})
  try:
    walker = Walker(context, demo.url)
    walker.goto(600)
    page = walker.page
    page.wait_for_selector(f"{CARD} .arena-row .arena-tail .pill")
    assert page.eval_on_selector(CARD, MODE) == "table-row"
    page.set_viewport_size({"width": 600, "height": 900})
    page.wait_for_function(f"{TABLE}.classList.contains('cards')")
    assert page.eval_on_selector(CARD, MODE) == "grid", "a narrow window folds the rows"
    page.set_viewport_size({"width": 1400, "height": 900})
    page.wait_for_function(f"!{TABLE}.classList.contains('cards')")
    assert page.eval_on_selector(CARD, MODE) == "table-row", "a wide one unfolds them"
  finally:
    context.close()
