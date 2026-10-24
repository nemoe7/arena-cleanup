"""The claim inputs show the built-in fallback as their placeholder.

An empty list names the defaults a run falls back to. An entry replaces the
placeholder, and its removal brings the defaults back (docs/design.md).
"""

from __future__ import annotations

import json
import urllib.request

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

PLACEHOLDER = "(id) => document.querySelector(`#${id} input`).placeholder"
BOXES = (("claim-emails", "emails"), ("claim-names", "names"))


def test_an_empty_list_shows_the_fallback_and_an_entry_replaces_it(
  desktop: Walker,
) -> None:
  page = desktop.page
  page.goto(f"{desktop.url}/#/settings", wait_until="networkidle")
  page.wait_for_selector("#card-claims")
  with urllib.request.urlopen(f"{desktop.url}/api/settings") as reply:
    claims = json.load(reply)["claims"]
  assert claims["emails"] == [] and claims["names"] == [], "the demo starts empty"
  for box, key in BOXES:
    fallback = ", ".join(claims["defaults"][key])
    assert page.evaluate(PLACEHOLDER, box) == fallback
    assert "falls back to the built-in rule" not in page.inner_text("#card-claims")
    page.fill(f"#{box} input", "someone")
    page.press(f"#{box} input", "Enter")
    assert page.evaluate(PLACEHOLDER, box) == "", "an entry replaces the fallback"
    page.click(f"#{box} button[aria-label='Remove someone']")
    assert page.evaluate(PLACEHOLDER, box) == fallback, "removal brings it back"
