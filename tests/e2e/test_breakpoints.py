"""Three named widths, one change each: 1200 stacks the cards, 900 stacks the page, 640 is the phone."""

from __future__ import annotations

import re
from typing import Any

import pytest

from scripts.walk import Demo, Walker

from ..conftest import ROOT

NAMED = {1200, 900, 640}
EM = 16  # the browser default the em queries read
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
  };
}"""


def test_only_the_named_widths_carry_rules() -> None:
  queries = re.findall(r"@media \(max-width: ([\d.]+)(px|em)\)", PAGE.read_text())
  assert {unit for _, unit in queries} == {"em"}, "em, so the switch follows the font"
  assert {int(float(w) * EM) for w, _ in queries} == NAMED


def probe(browser: Any, demo: Demo, width: int) -> dict[str, Any]:
  context = browser.new_context(viewport={"width": width, "height": 900})
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
  if width == 1200:
    assert (above["workColumns"], at["workColumns"]) == (2, 1)
    assert (above["pad"], at["pad"]) == ("20px", "16px")
    assert above["detailColumns"] == at["detailColumns"] == 2
  if width == 900:
    assert (above["detailColumns"], at["detailColumns"]) == (2, 1)
    assert above["workColumns"] == at["workColumns"] == 1
    assert above["body"] == at["body"]
  if width == 640:
    assert (above["body"], at["body"]) == ("14px", "15px")
    assert above["browse"] < 44 <= at["browse"]
    assert above["detailColumns"] == at["detailColumns"] == 1
    assert above["pad"] == at["pad"] == "16px", "the phone keeps the 16 px padding"
