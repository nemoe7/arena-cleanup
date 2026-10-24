"""The motion set: GSAP tweens on one curve, off under reduced motion.

A view fades in. The first cards, the first commits, and a dialog also rise
8 px, 180 ms on one curve. Reduced motion paints at once.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

DESKTOP = {"viewport": {"width": 1360, "height": 900}}
TWEENS = """(sel) => gsap.getTweensOf(document.querySelector(sel))
  .map((t) => [t.duration(), t.vars.ease])"""
OPACITY = "(sel) => getComputedStyle(document.querySelector(sel)).opacity"


def test_gsap_is_vendored_and_served_as_a_script(desktop: Walker) -> None:
  desktop.goto(1200)
  assert desktop.page.evaluate("gsap.version") == "3.15.0"
  reply = desktop.page.request.get(desktop.url.rstrip("/") + "/gsap.min.js")
  assert reply.ok
  assert reply.headers["content-type"].startswith("application/javascript")


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_a_view_enters_on_the_shared_curve(
  request: pytest.FixtureRequest, width: str
) -> None:
  walker: Walker = request.getfixturevalue(width)
  page = walker.page
  walker.goto(1200)
  page.click(".repo-card:has-text('shop-web') .repo-name")
  tweens = page.evaluate(TWEENS, "#view-repo")
  assert tweens == [[0.18, "power2.out"]], "one tween, 180 ms, one curve"
  assert float(page.evaluate(OPACITY, "#view-repo")) < 1
  page.wait_for_timeout(400)
  assert page.evaluate(OPACITY, "#view-repo") == "1"
  assert page.evaluate(TWEENS, "#view-repo") == [], (
    "the tween clears its props and ends"
  )
  walker.click("#back", 600)


def test_a_dialog_enters_the_same_way(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto(1200)
  page.click(".repo-card:has-text('billing-api') button.pill")
  assert page.evaluate(TWEENS, "#checks-modal") == [[0.18, "power2.out"]]
  page.wait_for_timeout(400)
  assert page.evaluate(OPACITY, "#checks-modal") == "1"
  page.keyboard.press("Escape")
  page.wait_for_function("!document.getElementById('checks-modal').open")


def test_reduced_motion_paints_at_once(browser: Any, desktop: Walker) -> None:
  context = browser.new_context(**DESKTOP, reduced_motion="reduce")
  try:
    page = context.new_page()
    page.goto(desktop.url, wait_until="networkidle")
    page.wait_for_selector(".repo-card")
    assert page.evaluate(TWEENS, "#repo-grid .repo-card") == []
    page.click(".repo-card:has-text('shop-web') .repo-name")
    assert page.evaluate(TWEENS, "#view-repo") == []
    assert page.evaluate(OPACITY, "#view-repo") == "1"
  finally:
    context.close()
