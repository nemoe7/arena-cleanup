"""The settings page: two columns above 1200 px, one below, and folded help cards."""

from __future__ import annotations

from typing import Any

import pytest

from scripts.walk import Demo, Walker

pytestmark = pytest.mark.e2e

SECTIONS = [
  "#identity-body",
  "#access-body",
  "#signing-body",
  "#claims-body",
  "#info-body",
]
PROBE = """(ids) => {
  const box = (s) => document.querySelector(s).getBoundingClientRect();
  return {
    height: document.documentElement.scrollHeight,
    tops: ids.map((s) => Math.round(box(s).top)),
    lefts: ids.map((s) => Math.round(box(s).left)),
    folds: [...document.querySelectorAll('details.fold')].map((d) => [d.querySelector('h2').textContent, d.open]),
  };
}"""


def probe(browser: Any, demo: Demo, width: int) -> dict[str, Any]:
  context = browser.new_context(viewport={"width": width, "height": 900})
  try:
    walker = Walker(context, f"{demo.url}/#/settings")
    walker.goto(800)
    walker.page.wait_for_selector("#card-identity")
    return walker.page.evaluate(PROBE, SECTIONS)
  finally:
    context.close()


def test_above_1200_the_settings_fill_two_columns(browser: Any, demo: Demo) -> None:
  wide = probe(browser, demo, 1280)
  identity, access, signing, claims, info = wide["tops"]
  assert identity == access, "the two columns start level"
  assert identity < claims < info, "left: Identity, Claimed commits, About"
  assert access < signing, "right: GitHub, then the keys"
  assert wide["lefts"][0] < wide["lefts"][1], "Identity left, GitHub right"
  assert wide["lefts"][0] == wide["lefts"][3] == wide["lefts"][4]
  narrow = probe(browser, demo, 1200)
  assert narrow["tops"] == sorted(narrow["tops"]), "one column keeps the old order"
  assert len(set(narrow["lefts"])) == 1
  assert wide["height"] < narrow["height"], "two columns make a shorter page"


def test_the_help_cards_fold(desktop: Walker) -> None:
  page = desktop.page
  page.goto(f"{desktop.url}/#/settings", wait_until="networkidle")
  page.wait_for_selector("#card-identity")
  folds = dict(page.evaluate(PROBE, SECTIONS)["folds"])
  assert folds == {"About": False}
  # helper and keys read in the GitHub card, no fold of their own
  assert desktop.count("#access-body .card") == 1
  assert "credential helper" in desktop.text("#access-body")
  assert "ssh keys" in desktop.text("#access-body")
  desktop.click("#info-body details.fold > summary", 200)
  assert (
    page.evaluate("() => document.querySelector('#info-body details.fold').open")
    is True
  )
  assert desktop.visible("#info-body details.fold .card-body")
  desktop.click("#info-body details.fold > summary", 200)
  assert not desktop.visible("#info-body details.fold .card-body")
  mark = page.eval_on_selector(
    "#info-body .fold-mark", "e => getComputedStyle(e, '::after').content"
  )
  assert mark == '"show"'
