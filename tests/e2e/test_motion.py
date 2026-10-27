"""The motion set: GSAP tweens on one curve, off under reduced motion.

A view fades in. The cards, the commits, and a dialog also rise 8 px, 180 ms
on one curve. A list spreads its rows over 120 ms. Reduced motion paints at
once.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.walk import Walker

pytestmark = [pytest.mark.e2e, pytest.mark.motion]

DESKTOP = {"viewport": {"width": 1360, "height": 900}}
TWEENS = """(sel) => gsap.getTweensOf(document.querySelector(sel))
  .map((t) => [t.duration(), t.vars.ease])"""
OPACITY = "(sel) => getComputedStyle(document.querySelector(sel)).opacity"
# a loaded test round trip outlives the 180 ms tween. The page records each
# entry at its start instead: target id, duration, ease, and first opacity.
HOOK = """() => {
  const real = gsap.fromTo;
  window.__entries = [];
  gsap.fromTo = (targets, from, to) => {
    const tween = real.call(gsap, targets, from, to);
    const first = [targets].flat()[0];
    window.__entries.push([first.id, tween.duration(), to.ease, getComputedStyle(first).opacity]);
    return tween;
  };
  window.__unhook = () => { gsap.fromTo = real; };
}"""
SETTLED = """(sel) => window.__entries.length
  && getComputedStyle(document.querySelector(sel)).opacity === '1'
  && !gsap.getTweensOf(document.querySelector(sel)).length"""


def entries(page: Any, sel: str) -> list[list[Any]]:
  """Wait until the hooked entry of `sel` ended, then return what the hook saw of it."""
  page.wait_for_function(SETTLED, arg=sel)
  page.evaluate("window.__unhook()")
  return [e for e in page.evaluate("window.__entries") if e[0] == sel.lstrip("#")]


def test_gsap_is_vendored_and_served_as_a_script(desktop: Walker) -> None:
  desktop.goto()
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
  walker.goto()
  page.evaluate(HOOK)
  page.click(".repo-card:has-text('shop-web') .repo-name")
  seen = entries(page, "#view-repo")
  assert seen == [["view-repo", 0.18, "power2.out", "0"]], (
    "one tween, 180 ms, one curve, from transparent"
  )
  assert page.evaluate(OPACITY, "#view-repo") == "1"
  assert page.evaluate(TWEENS, "#view-repo") == [], (
    "the tween clears its props and ends"
  )
  walker.click("#back")


def test_a_dialog_enters_the_same_way(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto()
  page.evaluate(HOOK)
  page.click(".repo-card:has-text('billing-api') button.pill")
  assert entries(page, "#modal") == [["modal", 0.18, "power2.out", "0"]]
  assert page.evaluate(OPACITY, "#modal") == "1"
  page.keyboard.press("Escape")
  page.wait_for_function("!document.getElementById('modal').open")


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


STAGGER_S = 0.12
# wrap gsap.fromTo, so the test sees which nodes a list enters and how
RECORD_ENTERS = """() => {
  window.__enters = [];
  const orig = gsap.fromTo;
  gsap.fromTo = (targets, from, to) => {
    const nodes = [targets].flat();
    const rows = nodes.filter((n) => n.classList?.contains('commit')).length;
    window.__enters.push([nodes.length, rows, to.stagger, to.duration]);
    return orig.call(gsap, targets, from, to);
  };
}"""
ROWS = "document.querySelectorAll('#commits .commit').length"


def test_every_commit_row_enters_within_one_spread(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto()
  page.evaluate(RECORD_ENTERS)
  page.click(".repo-card:has-text('shop-web') .repo-name")
  page.wait_for_selector("#commits .commit")
  page.wait_for_timeout(500)
  rows = page.evaluate(ROWS)
  assert rows > 12, "the demo page holds more rows than the old slice"
  enters = [e for e in page.evaluate("window.__enters") if e[1]]
  assert enters == [[rows, rows, {"amount": STAGGER_S}, 0.18]]
  assert page.evaluate(OPACITY, "#commits .commit:last-child") == "1"
  desktop.click("#back")
