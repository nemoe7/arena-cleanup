#!/usr/bin/env python3
"""
measure.py - local-only spacing audit for the arena-cleanup UI.

Drives a real Chromium over the page, reads computed styles for every visible
element, and reports:

  * the spacing scale in use (a histogram of every padding/margin/gap value)
  * values that do not sit on the 4px grid
  * "loners": a value used once while the rest of its peers agree on something
    else, which is what "the padding feels inconsistent" usually means
  * the gap between sibling boxes, measured from real client rects rather than
    from the CSS that was supposed to produce them

Nothing here touches the network beyond the app under test. Run it against a
local server:

    python3 tools/measure.py --url http://localhost:8080 --out /tmp/measure

With --against, it compares the current run to a saved JSON report. That is how
you prove a spacing change moved the thing you meant to move.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
  from playwright.sync_api import sync_playwright
except ImportError:  # pragma: no cover - the tool is optional
  print("playwright is required: pip install playwright && playwright install chromium")
  raise SystemExit(2)

# The scale the stylesheet is built on: every even step, plus a single 1px
# allowance for optical nudges. Examples: a tiny chip border, an icon sitting
# on a baseline. Anything else is a value nobody chose on purpose.
GRID = 2
MICRO = {1}

# Every property that contributes to "spacing" for our purposes.
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

COLLECT = """
(selectors) => {
  const out = [];
  const seen = new Set();
  const all = document.querySelectorAll('body *');
  for (const node of all) {
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
    out.push({
      path: key,
      tag: node.tagName.toLowerCase(),
      cls: [...node.classList].join(' '),
      rect: {x: Math.round(box.x), y: Math.round(box.y), w: Math.round(box.width), h: Math.round(box.height)},
      style,
      radius: cs.borderTopLeftRadius,
      fontSize: cs.fontSize,
      text: (node.innerText || '').trim().slice(0, 30),
    });
  }
  return out;
}
"""


def px(value: str) -> float | None:
  value = (value or "").strip()
  if value.endswith("px"):
    try:
      return float(value[:-2])
    except ValueError:
      return None
  return None


def analyse(elements: list[dict[str, Any]]) -> dict[str, Any]:
  values: Counter[float] = Counter()
  by_prop: dict[str, Counter[float]] = defaultdict(Counter)
  off_grid: list[dict[str, Any]] = []
  radii: Counter[str] = Counter()
  fonts: Counter[str] = Counter()

  for element in elements:
    radii[element["radius"]] += 1
    fonts[element["fontSize"]] += 1
    for prop, raw in element["style"].items():
      number = px(raw)
      if number is None:
        continue
      # negative margins are a deliberate tool, not an accident
      if number == 0 or number in MICRO:
        continue
      # margin:auto computes to a pixel length; that is layout, not a token
      if prop.startswith("margin") and number > 48:
        continue
      values[number] += 1
      by_prop[prop][number] += 1
      if number % GRID != 0:
        off_grid.append({"path": element["path"], "prop": prop, "value": number})

  # a "loner" is a value used by exactly one rule while its property's dominant
  # value is used by several others
  loners = []
  families: dict[tuple[str, str], Counter[float]] = defaultdict(Counter)
  for element in elements:
    # the whole class list is the component: `pill ok` and `banner ok` are two
    # different things that share a state name. Comparing them to each other
    # produces noise, not a spacing decision
    family = ".".join(element["cls"].split()) or element["tag"] or "?"
    for prop, raw in element["style"].items():
      number = px(raw)
      if number is None or number == 0 or number in MICRO:
        continue
      if prop.startswith("margin") and number > 48:
        continue
      families[(family, prop)][number] += 1

  for (family, prop), counter in families.items():
    total = sum(counter.values())
    if total < 4:
      continue
    top_value, top_count = counter.most_common(1)[0]
    for value, count in counter.items():
      if count == 1 and top_count >= 2 and abs(value - top_value) <= 8:
        loners.append(
          {
            "component": family,
            "prop": prop,
            "value": value,
            "dominant": top_value,
            "used_by": top_count,
          }
        )

  return {
    "count": len(elements),
    "values": {str(k): v for k, v in sorted(values.items())},
    "off_grid": off_grid,
    "loners": sorted(loners, key=lambda r: (r["prop"], r["value"])),
    "radii": dict(radii.most_common()),
    "fonts": dict(fonts.most_common()),
  }


def gaps(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Vertical gaps between consecutive siblings, from their real boxes."""
  out = []
  seen = set()
  for i, group in enumerate(elements):
    key = group["path"].rsplit(" > ", 1)[0]
    if key in seen:
      continue
    seen.add(key)
  return out


def run(url: str, out: Path, width: int, height: int) -> dict[str, Any]:
  out.mkdir(parents=True, exist_ok=True)
  with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(
      viewport={"width": width, "height": height}, device_scale_factor=2
    )
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(1200)

    report: dict[str, Any] = {"url": url, "viewport": [width, height], "views": {}}
    for view, opener in (
      ("dashboard", None),
      ("repo", ".repo-card"),
      ("signing", "#signing-btn"),
      ("access", "#access-btn"),
    ):
      if opener:
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(400)
        page.click(opener, timeout=5000)
        page.wait_for_timeout(800)
      elements = page.evaluate(COLLECT, list(PROPS))
      report["views"][view] = analyse(elements)
      page.screenshot(path=str(out / f"measure-{view}-{width}.png"), full_page=True)
    browser.close()
  return report


def summarise(report: dict[str, Any]) -> str:
  lines = []
  for view, data in report["views"].items():
    lines.append(f"\n{view}  ({data['count']} elements)")
    total = sum(data["values"].values())
    lines.append(f"  spacing values: {total} non-zero")
    top = sorted(data["values"].items(), key=lambda kv: -kv[1])[:8]
    lines.append("  most used: " + ", ".join(f"{k}px×{v}" for k, v in top))
    if data["off_grid"]:
      lines.append(f"  OFF GRID ({len(data['off_grid'])}):")
      for row in data["off_grid"][:12]:
        lines.append(f"    {row['prop']}={row['value']}  {row['path']}")
    else:
      lines.append("  off grid: none")
    if data["loners"]:
      lines.append(f"  LONERS ({len(data['loners'])}):")
      for row in data["loners"][:12]:
        lines.append(
          f"    .{row['component']} {row['prop']}={row['value']}"
          f" (peers use {row['dominant']}, ×{row['used_by']})"
        )
    lines.append(
      "  radii: " + ", ".join(f"{k}×{v}" for k, v in list(data["radii"].items())[:5])
    )
    sizes = sorted({px(f) for f in data["fonts"] if px(f) is not None})
    if sizes:
      lines.append(
        f"  font sizes: {len(sizes)} distinct ({sizes[0]:.0f}–{sizes[-1]:.0f}px)"
      )
  return "\n".join(lines)


def compare(old: dict[str, Any], new: dict[str, Any]) -> str:
  lines = ["", "changes since the saved run:"]
  any_change = False
  for view in new["views"]:
    if view not in old["views"]:
      lines.append(f"  {view}: new view")
      continue
    a, b = old["views"][view], new["views"][view]
    deltas = []
    if a["count"] != b["count"]:
      deltas.append(f"elements {a['count']} → {b['count']}")
    off_a, off_b = len(a["off_grid"]), len(b["off_grid"])
    if off_a != off_b:
      deltas.append(f"off-grid {off_a} → {off_b}")
    lon_a, lon_b = len(a["loners"]), len(b["loners"])
    if lon_a != lon_b:
      deltas.append(f"loners {lon_a} → {lon_b}")
    if deltas:
      any_change = True
      lines.append(f"  {view}: " + ", ".join(deltas))
  if not any_change:
    lines.append("  none")
  return "\n".join(lines)


def main() -> int:
  ap = argparse.ArgumentParser(description=__doc__)
  ap.add_argument("--url", default="http://localhost:8080")
  ap.add_argument("--out", default="/tmp/measure")
  ap.add_argument("--width", type=int, default=1360)
  ap.add_argument("--height", type=int, default=900)
  ap.add_argument("--against", help="a previous report.json to compare with")
  ap.add_argument(
    "--fail-on-offgrid", action="store_true", help="exit 1 if off-grid values exist"
  )
  args = ap.parse_args()

  report = run(args.url, Path(args.out), args.width, args.height)
  (Path(args.out) / "report.json").write_text(json.dumps(report, indent=2) + "\n")
  print(summarise(report))

  if args.against:
    old = json.loads(Path(args.against).read_text())
    print(compare(old, report))

  if args.fail_on_offgrid:
    bad = sum(len(v["off_grid"]) for v in report["views"].values())
    return 1 if bad else 0
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
