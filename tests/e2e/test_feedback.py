"""The page's feedback lines: the offline banner and its retry button."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from scripts.walk import Walker

REPOS_API = "**/api/repos"


@pytest.fixture
def offline(desktop: Walker) -> Iterator[Walker]:
  desktop.page.route(REPOS_API, lambda route: route.abort())
  yield desktop
  desktop.page.unroute(REPOS_API)


def test_the_offline_banner_puts_retry_on_its_own_line(offline: Walker) -> None:
  offline.goto(800)
  assert offline.visible("#offline-banner #retry")
  lines = offline.text("#offline-banner").strip().splitlines()
  assert lines[0].endswith("then retry.") and lines[-1] == "Retry"
  lead = offline.page.eval_on_selector(
    "#offline-banner b", "e => e.getBoundingClientRect().bottom"
  )
  button = offline.page.eval_on_selector("#retry", "e => e.getBoundingClientRect().top")
  assert button >= lead, "the button shares a line with the text"
