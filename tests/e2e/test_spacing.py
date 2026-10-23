"""Spacing and type audit over the computed styles of every visible element.

The stylesheet follows an even scale with a single 1 px allowance. It has
one type ramp per width class (docs/design.md). Anything else is a value nobody
chose on purpose.
"""

from __future__ import annotations

from typing import Any

import pytest

from .conftest import Walker

pytestmark = pytest.mark.e2e

GRID = 2
MICRO = {1.0}
LAYOUT_MARGIN_PX = (
  48  # margin:auto computes to a pixel length. That is layout, not a token
)
DESKTOP_RAMP = {12.0, 13.0, 14.0, 16.0, 20.0}
PHONE_RAMP = {12.0, 13.0, 14.0, 15.0, 16.0, 19.0}
PROPS = (
  "padding-top",
  "padding-right",
  "padding-bottom",
  "padding-left",
  "margin-top",
  "margin-right",
  "margin-bottom",
  "margin-left",
  "row-gap",
  "column-gap",
)
VIEWS = {
  "dashboard": None,
  "repo": ".repo-card",
  "settings": "#settings-btn",
}

COLLECT = """
(selectors) => {
  const out = [];
  const seen = new Set();
  for (const node of document.querySelectorAll('body *')) {
    const box = node.getBoundingClientRect();
    const cs = getComputedStyle(node);
    if (box.width === 0 || box.height === 0) continue;
    if (cs.visibility === 'hidden' || cs.display === 'none') continue;
    const path = [];
    let cur = node;
    while (cur && cur.nodeType === 1 && path.length < 5) {
      let part = cur.tagName.toLowerCase();
      if (cur.id) part += '#' + cur.id;
      else if (cur.classList.length) part += '.' + [...cur.classList].slice(0, 2).join('.');
      path.unshift(part);
      cur = cur.parentElement;
    }
    const key = path.join(' > ');
    if (seen.has(key)) continue;
    seen.add(key);
    const style = {};
    for (const prop of selectors) style[prop] = cs.getPropertyValue(prop).trim();
    out.push({ path: key, style, fontSize: cs.fontSize });
  }
  return out;
}
"""


def px(value: str) -> float | None:
  value = (value or "").strip()
  if not value.endswith("px"):
    return None
  try:
    return float(value[:-2])
  except ValueError:
    return None


def off_grid(elements: list[dict[str, Any]]) -> list[tuple[str, str, float]]:
  """Spacing values that sit on neither the even scale nor the 1 px allowance."""
  found = []
  for element in elements:
    for prop, raw in element["style"].items():
      number = px(raw)
      if number is None or number == 0 or number in MICRO:
        continue
      if prop.startswith("margin") and number > LAYOUT_MARGIN_PX:
        continue
      if number % GRID != 0:
        found.append((element["path"], prop, number))
  return found


def font_sizes(elements: list[dict[str, Any]]) -> set[float]:
  return {size for size in (px(e["fontSize"]) for e in elements) if size is not None}


def collect(walker: Walker, opener: str | None) -> list[dict[str, Any]]:
  walker.goto(400 if opener else 1200)
  if opener:
    walker.click(opener, 800)
  return walker.page.evaluate(COLLECT, list(PROPS))


@pytest.mark.parametrize("view", list(VIEWS))
def test_desktop_spacing_sits_on_the_even_scale(desktop: Walker, view: str) -> None:
  elements = collect(desktop, VIEWS[view])
  assert elements
  assert off_grid(elements) == []
  assert font_sizes(elements) <= DESKTOP_RAMP


@pytest.mark.parametrize("view", list(VIEWS))
def test_phone_spacing_sits_on_the_even_scale(phone: Walker, view: str) -> None:
  elements = collect(phone, VIEWS[view])
  assert elements
  assert off_grid(elements) == []
  assert font_sizes(elements) <= PHONE_RAMP
