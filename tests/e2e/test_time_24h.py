"""Commit dates read in 24-hour time, with no AM or PM (docs/design.md)."""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

ISO = "2026-10-24T18:11:00+00:00"
DATE = re.compile(r"^[A-Z][a-z]{2} \d{1,2}, \d{2}:\d{2}$")
LOCAL_HOUR = f"() => String(new Date({json.dumps(ISO)}).getHours()).padStart(2, '0')"


def page_body() -> dict[str, Any]:
  commit = {
    "sha": "a" * 40,
    "short": "a" * 7,
    "subject": "an afternoon commit",
    "author": "demo",
    "date": ISO,
    "signed": False,
    "avatar": None,
  }
  return {"branch": "main", "total": 1, "shown": 1, "next": None, "commits": [commit]}


def test_a_commit_date_uses_the_24_hour_clock(desktop: Walker) -> None:
  page = desktop.page
  page.route(
    "**/api/repos/*/commits?*",
    lambda route: route.fulfill(
      status=200, content_type="application/json", body=json.dumps(page_body())
    ),
  )
  desktop.goto()
  desktop.click(".repo-card:has-text('shop-web') .repo-name")
  shown = desktop.text("#commits .commit .meta > span:last-child")
  assert DATE.match(shown), shown
  assert f", {page.evaluate(LOCAL_HOUR)}:11" in shown
  assert "AM" not in shown and "PM" not in shown
