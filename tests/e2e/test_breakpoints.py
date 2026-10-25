"""Three named widths, one change each: 1088 stacks the cards, 960 stacks the page, 480 is the phone.

A fourth query reads the height: under 384 px, top bar and sidebar scroll with the page.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from scripts.walk import Demo, Walker

from ..conftest import ROOT

NAMED = {1088, 960, 480}
SHORT = 384  # 24em, nuu's landscape touch height
EM = 16  # the browser default that em queries read
PAGE = ROOT / "ui" / "static" / "index.html"
PROBE = """() => {
  const cols = (s) => getComputedStyle(document.querySelector(s)).gridTemplateColumns.split(' ').length;
  return {
    workColumns: cols('.work'),
    optionColumns: cols('#options'),
    detailColumns: cols('.detail'),
    pad: getComputedStyle(document.documentElement).getPropertyValue('--pad').trim(),
    body: getComputedStyle(document.body).fontSize,
    browse: document.querySelector('#browse').getBoundingClientRect().height,
    topbar: getComputedStyle(document.querySelector('.topbar')).position,
    sidebar: getComputedStyle(document.querySelector('.sidebar')).position,
  };
}"""


def test_only_the_named_widths_carry_rules() -> None:
  queries = re.findall(r"@media \(max-width: ([\d.]+)(px|em)\)", PAGE.read_text())
  assert {unit for _, unit in queries} == {"em"}, "em, so the switch follows the font"
  assert {int(float(w) * EM) for w, _ in queries} == NAMED


def probe(browser: Any, demo: Demo, width: int, height: int = 900) -> dict[str, Any]:
  context = browser.new_context(viewport={"width": width, "height": height})
  try:
    walker = Walker(context, demo.url)
    walker.goto(400)
    walker.click(".repo-card .repo-name", 800)
    return walker.page.evaluate(PROBE)
  finally:
    context.close()


@pytest.mark.parametrize("width", sorted(NAMED))
def test_each_named_width_carries_one_change(
  browser: Any, demo: Demo, width: int
) -> None:
  above = probe(browser, demo, width + 1)
  at = probe(browser, demo, width)
  assert above["optionColumns"] == at["optionColumns"] == 1, "one column of options"
  if width == 1088:
    assert (above["workColumns"], at["workColumns"]) == (2, 1)
    assert (above["pad"], at["pad"]) == ("20px", "16px")
    assert above["detailColumns"] == at["detailColumns"] == 2
  if width == 960:
    assert (above["detailColumns"], at["detailColumns"]) == (2, 1)
    assert above["workColumns"] == at["workColumns"] == 1
    assert above["body"] == at["body"]
  if width == 480:
    assert (above["body"], at["body"]) == ("14px", "15px")
    assert above["browse"] < 44 <= at["browse"]
    assert above["detailColumns"] == at["detailColumns"] == 1
    assert above["pad"] == at["pad"] == "16px", "the phone keeps the 16 px padding"


def test_a_short_viewport_lets_the_bars_scroll_away(browser: Any, demo: Demo) -> None:
  tall = probe(browser, demo, 1280, SHORT + 1)
  short = probe(browser, demo, 1280, SHORT)
  assert (tall["topbar"], short["topbar"]) == ("sticky", "static")
  assert (tall["sidebar"], short["sidebar"]) == ("sticky", "static")
  assert tall["detailColumns"] == short["detailColumns"] == 2, "the width rules hold"
