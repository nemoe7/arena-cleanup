#!/usr/bin/env python3
"""Draw the app icon set under ui/static/icons/ from the Lucide broom-sparkles glyph.

The regular pictures carry the accent glyph alone on a transparent ground. The
maskable picture and the Apple touch icon add the dark background, full bleed.
Their glyph sits inside the safe zone of a launcher mask.

  uv run scripts/app_icon.py                        # writes ui/static/icons/*.png
  uv run scripts/app_icon.py --out /tmp/icons --chromium /path/to/chrome

It needs Playwright: `uv sync --group qa`, then `uv run playwright install
chromium`, or `--chromium` with a Chromium binary of your own.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.walk import launch_browser

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "ui" / "static" / "icons"
ACCENT = "#6e79d6"
BACKGROUND = "#0d0f12"
# Lucide 1.61.0 broom-sparkles, ISC licence in ui/static/LICENSE-lucide.txt.
# The page draws the same paths in its top bar mark.
GLYPH = (
  "M11 2v2",
  "M12 3h-2",
  "M13.5 10.5 22 2",
  (
    "M14.734 13.841a2 2 0 00-.314-2.42L12.58 9.58a2 2 0 00-2.421-.314l-7.657 4.461"
    "A1 1 0 002.3 15.3l6.403 6.403a1 1 0 001.571-.204z"
  ),
  "M20 15v4",
  "M22 17h-4",
  "M4 4v4",
  "m5 18 2-2",
  "M6 6H2",
  "m7.699 10.7 5.602 5.601",
)
GRID = 24  # the Lucide drawing grid
# name -> (pixel size, padding as a share of the side, background)
PICTURES = {
  "favicon-32.png": (32, 0.0, False),
  "icon-192.png": (192, 0.0, False),
  "icon-512.png": (512, 0.0, False),
  "apple-touch-icon.png": (180, 0.17, True),
  "icon-maskable-512.png": (512, 0.22, True),
}


def svg(size: int, pad: float, background: bool) -> str:
  """One picture: an optional full-bleed ground and the glyph scaled into the box."""
  inner = size * (1 - 2 * pad)
  scale = inner / GRID
  offset = size * pad
  ground = (
    f'<rect width="{size}" height="{size}" fill="{BACKGROUND}"/>' if background else ""
  )
  paths = "".join(f'<path d="{d}"/>' for d in GLYPH)
  return (
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
    f'viewBox="0 0 {size} {size}">{ground}'
    f'<g transform="translate({offset} {offset}) scale({scale})" fill="none" '
    f'stroke="{ACCENT}" stroke-width="2" stroke-linecap="round" '
    f'stroke-linejoin="round">{paths}</g></svg>'
  )


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument(
    "--out", type=Path, default=OUT, help="icon directory (default ui/static/icons)"
  )
  parser.add_argument(
    "--chromium",
    default=os.environ.get("WALK_CHROMIUM"),
    help="a Chromium binary to use instead of the one `playwright install` fetched",
  )
  args = parser.parse_args()
  from playwright.sync_api import sync_playwright

  args.out.mkdir(parents=True, exist_ok=True)
  with sync_playwright() as playwright:
    browser = launch_browser(playwright, args.chromium)
    page = browser.new_page(
      viewport={"width": 600, "height": 600}, device_scale_factor=1
    )
    for name, (size, pad, background) in PICTURES.items():
      page.set_content(f'<body style="margin:0">{svg(size, pad, background)}</body>')
      page.locator("svg").screenshot(path=str(args.out / name), omit_background=True)
      print(f"wrote {args.out / name}")
    browser.close()
  return 0


if __name__ == "__main__":
  sys.exit(main())
