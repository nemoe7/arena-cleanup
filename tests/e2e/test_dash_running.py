"""A dashboard row shows a clean in flight on its repo.

The server flags a repo with a live job. The row answers with an amber pill,
a greyed Clean & Push that names the reason, and aria-busy. The return from
the repo view reads the list again, so the row shows a run started there
(docs/design.md).
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

REPO = "shop-web"
CARD = f".repo-card:has-text('{REPO}')"
ROW = (
  "(card) => ({ busy: card.getAttribute('aria-busy'),"
  " pill: (card.querySelector('.pill.busy') || {}).textContent || null,"
  " disabled: card.querySelector('button.clean').disabled,"
  " title: card.querySelector('button.clean').title })"
)
REASON = "a clean is running on this repo"


def test_a_live_job_marks_its_row(desktop: Walker) -> None:
  page = desktop.page
  reads: list[Any] = []

  def flag(route: Any) -> None:
    reply = route.fetch()
    repos = reply.json()
    for repo in repos:
      repo["running"] = repo["name"] == REPO
    reads.append(len(repos))
    route.fulfill(response=reply, body=json.dumps(repos))

  # first paint comes from the fetch, later reads from the list
  page.route("**/api/fetch", flag)
  page.route("**/api/repos", flag)
  try:
    desktop.goto(1200)
    page.wait_for_selector(f"{CARD} .pill.busy")
    row = page.eval_on_selector(CARD, ROW)
    assert row == {
      "busy": "true",
      "pill": "clean running",
      "disabled": True,
      "title": REASON,
    }
    other = page.eval_on_selector(".repo-card:has-text('billing-api')", ROW)
    assert other["busy"] is None and other["pill"] is None, "one row alone"
    # repo view and back: the return reads the statuses once more
    before = len(reads)
    desktop.click(f"{CARD} .repo-name", 600)
    desktop.click("#back", 600)
    page.wait_for_selector(f"{CARD} .pill.busy")
    deadline = time.monotonic() + 5
    while len(reads) < before + 1 and time.monotonic() < deadline:
      page.wait_for_timeout(100)
    assert len(reads) == before + 1, "one fresh read on return"
  finally:
    page.unroute("**/api/repos")
    page.unroute("**/api/fetch")
  desktop.goto(1200)
  page.wait_for_selector(CARD)
  assert page.eval_on_selector(CARD, ROW)["pill"] is None, "a plain reload clears it"
