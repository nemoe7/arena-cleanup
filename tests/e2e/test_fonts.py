"""Bundled fonts: both faces load from the app itself (docs/design.md)."""

from __future__ import annotations

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

FACES = """async () => {
  await document.fonts.ready;
  const out = {};
  for (const face of document.fonts) {
    if (face.family.includes("Fallback")) continue;
    out[face.family] = face.status;
  }
  return out;
}"""
FAMILY = "e => getComputedStyle(e).fontFamily.split(',')[0].replace(/\"/g, '')"


def test_both_bundled_faces_are_loaded(desktop: Walker) -> None:
  desktop.goto()
  desktop.page.wait_for_selector(".repo-card .bname")
  assert desktop.page.evaluate(FACES) == {
    "Inter": "loaded",
    "Monaspace Neon": "loaded",
  }
  assert desktop.page.eval_on_selector("body", FAMILY) == "Inter"
  assert desktop.page.eval_on_selector(".repo-card .bname", FAMILY) == (
    "Monaspace Neon"
  )
