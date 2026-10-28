"""The commit list: the count hint with separators, 30 per page, older pages on scroll."""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.e2e.harness import Walker

pytestmark = pytest.mark.e2e

PAGE = 30
TOTAL = 1234
FIRST = "a" * 40
LAST_OF_FIRST = "b" * 40
LAST_OF_SECOND = "c" * 40
ROWS_JS = "document.querySelectorAll('#commits .commit').length"
ROWS = f"() => {ROWS_JS}"
# shop-web opens with arena/3f7c2e1a-shop-web selected, so every page names that ref
REF = "&ref=arena%2F3f7c2e1a-shop-web"


def commit(i: int, sha: str) -> dict[str, Any]:
  return {
    "sha": sha,
    "short": sha[:7],
    "subject": f"commit {i}",
    "author": "demo",
    "date": "2026-10-23T00:00:00+00:00",
    "signed": False,
    "avatar": None,
  }


def page_of(sha_last: str, nxt: str | None) -> dict[str, Any]:
  commits = [commit(i, f"{i:040x}") for i in range(PAGE - 1)] + [commit(PAGE, sha_last)]
  return {
    "branch": "main",
    "total": TOTAL,
    "shown": PAGE,
    "next": nxt,
    "commits": commits,
  }


def test_the_hint_is_the_count_and_a_scroll_loads_the_older_page(
  desktop: Walker,
) -> None:
  page = desktop.page
  urls: list[str] = []

  def fake(route: Any) -> None:
    urls.append(route.request.url)
    before = (
      route.request.url.split("before=")[-1] if "before=" in route.request.url else ""
    )
    body = (
      page_of(LAST_OF_SECOND, None) if before else page_of(LAST_OF_FIRST, LAST_OF_FIRST)
    )
    route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

  page.route("**/api/repos/*/commits?*", fake)
  desktop.goto()
  desktop.click(".repo-card:has-text('shop-web') .repo-name")
  page.wait_for_function(f"{ROWS_JS} === {PAGE}")
  assert desktop.text("#commits-hint") == f"{TOTAL:,}"
  assert page.evaluate(ROWS) == PAGE
  assert urls[-1].endswith(f"limit={PAGE}{REF}")
  # scroll to the end: one request with the cursor, older page appended below
  page.eval_on_selector("#commits", "e => { e.scrollTop = e.scrollHeight; }")
  page.wait_for_function(f"{ROWS_JS} === {2 * PAGE}")
  assert urls[-1].endswith(f"limit={PAGE}{REF}&before={LAST_OF_FIRST}")
  assert len(urls) == 2
  # the last page has no cursor, so a further scroll asks for nothing.
  # The Reload that follows restarts at the first page.
  page.eval_on_selector(
    "#commits", "e => { e.scrollTop = 0; e.scrollTop = e.scrollHeight; }"
  )
  desktop.click("#commits-refresh")
  page.wait_for_function(f"{ROWS_JS} === {PAGE}")
  assert len(urls) == 3, "the scroll asked for nothing, the Reload once"
  assert urls[-1].endswith(f"limit={PAGE}{REF}")
  page.unroute("**/api/repos/*/commits?*")
