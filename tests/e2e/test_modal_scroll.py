"""The page under an open dialog holds its scroll position.

A dialog sits in the top layer, so the root has to drop its own scroll while
one is open. On a phone the page scrolls as one. A wheel turn over the scrim
moves nothing there, and the page scrolls again once the dialog closes.
"""

from __future__ import annotations

import pytest

from scripts.walk import Walker
from tests.e2e.test_phase_modals import RUN, close_phase, open_phase, open_run

pytestmark = pytest.mark.e2e

TOP = "() => document.scrollingElement.scrollTop"
ROOT_OVERFLOW = "() => getComputedStyle(document.documentElement).overflow"


def test_the_page_holds_still_under_an_open_dialog(phone: Walker) -> None:
  page = phone.page
  open_run(phone, RUN)
  open_phase(phone, "prepare")
  assert page.evaluate(ROOT_OVERFLOW) == "hidden"
  start = page.evaluate(TOP)
  page.mouse.move(40, 40)
  page.mouse.wheel(0, 300)
  page.wait_for_timeout(250)
  assert page.evaluate(TOP) == start, "the wheel moved the page under the dialog"
  close_phase(phone)
  assert page.evaluate(ROOT_OVERFLOW) != "hidden"
  page.mouse.wheel(0, -300 if start > 0 else 300)
  page.wait_for_function(f"() => document.scrollingElement.scrollTop !== {start}")
