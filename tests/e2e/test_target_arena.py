"""The target select never offers an arena branch as the current branch.

A clone parked on an arena branch gets the default branch alone. The page
selects it and sends it as `-b`. A clone parked on any other branch keeps
that branch as `current` beside the default (docs/design.md).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

PARKED = {"shop-web": "arena/9a0e5c3b-shop-web", "billing-api": "feature/invoices"}
CARD = ".repo-card:has-text('{name}') .repo-name"
ROUTES = ("**/api/fetch", "**/api/repos", "**/api/repos/*")
SELECT = "(s) => ({ value: s.value, options: [...s.options].map((o) => [o.value, o.textContent]) })"


def test_an_arena_branch_is_never_the_current_target(desktop: Walker) -> None:
  page = desktop.page

  def park(route: Any) -> None:
    reply = route.fetch()
    data = reply.json()
    for repo in data if isinstance(data, list) else [data]:
      if repo.get("name") in PARKED:
        repo["status"]["branch"] = PARKED[repo["name"]]
    route.fulfill(response=reply, body=json.dumps(data))

  for pattern in ROUTES:
    page.route(pattern, park)
  try:
    desktop.goto()
    desktop.click(CARD.format(name="shop-web"))
    select = page.eval_on_selector("#branch", SELECT)
    assert select == {"value": "main", "options": [["main", "main (default)"]]}
    # parked on a plain branch, the clone keeps it as the current target
    desktop.click("#back")
    desktop.click(CARD.format(name="billing-api"))
    select = page.eval_on_selector("#branch", SELECT)
    assert select == {
      "value": "",
      "options": [["main", "main (default)"], ["", "current (feature/invoices)"]],
    }
  finally:
    for pattern in ROUTES:
      page.unroute(pattern)
