"""The Commits list follows the selected arena branch.

The list reads the arena branch on origin, the commits a clean would take,
not the clone's HEAD. A click on another arena row reloads it, and a repo
with no arena branch falls back to HEAD.
"""

from __future__ import annotations

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

FIRST = "() => document.querySelector('#commits .commit .subject').textContent"
ROW = '#sidebar .row-btn[data-branch="arena/session-5"]'


def subjects(walker: Walker, repo_id: str, ref: str) -> list[str]:
  res = walker.page.request.get(
    f"{walker.url}/api/repos/{repo_id}/commits?limit=3&ref={ref}"
  )
  return [c["subject"] for c in res.json()["commits"]]


def test_the_list_shows_the_selected_arena_branch(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto(1200)
  repos = page.request.get(f"{desktop.url}/api/repos").json()
  repo_id = next(r["id"] for r in repos if r["name"] == "data-pipeline")
  desktop.click(".repo-card:has-text('data-pipeline') .repo-name", 800)
  assert page.evaluate(FIRST) == subjects(desktop, repo_id, "arena/session-6")[0]
  page.click(ROW)
  want = subjects(desktop, repo_id, "arena/session-5")[0]
  page.wait_for_function(
    f"document.querySelector('#commits .commit .subject').textContent === {want!r}"
  )
