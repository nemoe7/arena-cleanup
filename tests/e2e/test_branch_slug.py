"""An arena branch named arena/<slug>-<repo> reads as its slug.

The card row and the sidebar row show the slug, and the full name stays in
their title. A branch with any other shape keeps its full name. Commands,
data attributes, and the delete dialog keep the full name (docs/design.md).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

REPO = "shop-web"
FULL = "arena/9f2c7a1e-shop-web"
SLUG = "9f2c7a1e"
PLAIN = "arena/session-2"
# the probed repo takes a fresh slug name, and docs-site a name without the repo tail
RENAMES = {
  REPO: ("arena/3f7c2e1a-shop-web", FULL),
  "docs-site": ("arena/2a6e8f3d-docs-site", PLAIN),
}
CARD = f".repo-card:has-text('{REPO}')"
OTHER = ".repo-card:has-text('docs-site')"
ROW = f'#sidebar .row-btn[data-branch="{FULL}"]'
NAME = "(e) => [e.textContent, e.title]"


def rename(route: Any) -> None:
  """Each renamed repo's arena branch takes its new name in every status field."""
  reply = route.fetch()
  data = reply.json()
  for repo in data if isinstance(data, list) else [data]:
    status = repo.get("status") or {}
    old, new = RENAMES.get(repo.get("name"), (None, None))
    if old not in status.get("arena", []):
      continue
    status["arena"] = [new if b == old else b for b in status["arena"]]
    for field in ("ahead", "pr", "tips"):
      if old in status.get(field, {}):
        status[field][new] = status[field].pop(old)
  route.fulfill(response=reply, body=json.dumps(data))


def test_an_arena_branch_reads_as_its_slug(desktop: Walker) -> None:
  page = desktop.page
  for pattern in ("**/api/fetch", "**/api/repos", "**/api/repos/*"):
    page.route(pattern, rename)
  try:
    desktop.goto(1200)
    page.wait_for_selector(f"{CARD} .arena-row .bname")
    assert page.eval_on_selector(f"{CARD} .arena-row .bname", NAME) == [SLUG, FULL], (
      "the card row shows the slug and keeps the full name as its title"
    )
    assert page.eval_on_selector(f"{OTHER} .arena-row .bname", NAME) == [
      PLAIN,
      PLAIN,
    ], "a branch without the repo name tail keeps its full name"
    desktop.click(f"{CARD} .repo-name", 600)
    page.wait_for_selector(ROW)
    assert page.eval_on_selector(f"{ROW} .txt", "(e) => e.textContent") == SLUG
    assert page.eval_on_selector(ROW, NAME)[1] == f"Pull from {FULL}", (
      "the sidebar row names the full branch in its title"
    )
    label = page.eval_on_selector(
      f"{ROW} ~ .arena-del", "(e) => e.getAttribute('aria-label')"
    )
    assert label == f"Delete {FULL}", "the delete control names the full branch"
  finally:
    page.unroute_all(behavior="ignoreErrors")
