#!/usr/bin/env python3
"""Shoot the four example views of the design boards from a fresh demo.

  uv run scripts/views.py --out docs/shots/views
  uv run scripts/views.py --out docs/shots/views --chromium /path/to/chrome

`docs/boards.json` embeds the four PNG files in the views board. The script
needs Playwright: `uv sync --group qa`, then `uv run playwright install
chromium`, or `--chromium` with a Chromium binary of your own.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e.harness import DESKTOP, Demo, Walker, launch_browser


def capture_views(walker: Walker, demo: Demo) -> dict[str, bytes]:
  """The four example views of the design boards, PNG bytes by shot name."""
  shots: dict[str, bytes] = {}
  walker.goto()
  shots["dashboard"] = walker.page.screenshot()
  demo.sign_in(False)
  demo.wait_until_checked(False)
  walker.goto()
  shots["signed-out"] = walker.page.screenshot()
  demo.sign_in(True)
  demo.wait_until_checked(True)
  walker.goto()
  walker.click(".repo-card .repo-name")
  walker.click('input[data-opt="dry_run"]')
  walker.click("#start")
  walker.wait_status("exit")
  walker.page.wait_for_timeout(400)
  shots["after-run"] = walker.page.screenshot(full_page=True)
  walker.click("#settings-btn")
  shots["settings"] = walker.page.screenshot(full_page=True)
  return shots


def views(out: Path, chromium: str | None) -> int:
  from playwright.sync_api import sync_playwright

  out.mkdir(parents=True, exist_ok=True)
  with tempfile.TemporaryDirectory(prefix="views-demo-") as tmp:
    demo = Demo(Path(tmp) / "demo")
    try:
      with sync_playwright() as playwright:
        browser = launch_browser(playwright, chromium)
        walker = Walker(browser.new_context(**DESKTOP), demo.url)
        shots = capture_views(walker, demo)
        browser.close()
    finally:
      demo.stop()
  if walker.errors:
    print("console errors while capturing:", *walker.errors, sep="\n  ")
    return 1
  for name, png in shots.items():
    (out / f"{name}.png").write_bytes(png)
  print(f"views: {len(shots)} shots -> {out}")
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument("--out", required=True, type=Path, help="the PNG directory")
  parser.add_argument(
    "--chromium",
    default=os.environ.get("E2E_CHROMIUM"),
    help="a Chromium binary to use instead of the one `playwright install` fetched",
  )
  args = parser.parse_args()
  return views(args.out, args.chromium)


if __name__ == "__main__":
  sys.exit(main())
