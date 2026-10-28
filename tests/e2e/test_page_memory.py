"""Page memory: commit pages, the settings answers, and the last run paint at once.

The key of a commit page is repo, ref, tip, and cursor. A return to a branch
makes no request, and Reload makes one. Settings and signing paint their last
answer while the fresh read runs.

A repo view paints its last finished run before the server names the latest
one. Another run repaints the view (docs/design.md).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.e2e.harness import Walker

pytestmark = pytest.mark.e2e

PIPELINE = ".repo-card:has-text('data-pipeline') .repo-name"
SHOP = ".repo-card:has-text('shop-web') .repo-name"
ROW = ".row-btn.select[data-branch='{branch}']"
ROWS = "#log .log-row"
LOADING = "document.querySelector('#signing-body').innerText.includes('loading')"


def hits(page: Any, token: str) -> list[str]:
  seen: list[str] = []
  page.on("request", lambda req: seen.append(req.url) if token in req.url else None)
  return seen


def test_a_branch_seen_before_paints_its_commits_from_memory(desktop: Walker) -> None:
  page = desktop.page
  seen = hits(page, "/commits?")
  desktop.goto()
  desktop.click(PIPELINE)
  page.wait_for_selector("#commits .commit")
  first = len(seen)
  assert first == 1, "one page for the selected branch"
  desktop.click(ROW.format(branch="arena/5e1f7d2c-data-pipeline"))
  page.wait_for_selector("#commits .commit")
  assert len(seen) == first + 1, "a new branch reads its page"
  desktop.click(ROW.format(branch="arena/6d8b3a4e-data-pipeline"))
  page.wait_for_selector("#commits .commit")
  assert len(seen) == first + 1, "a branch seen before paints from memory"
  desktop.click("#commits-refresh")
  assert len(seen) == first + 2, "Reload reads afresh"
  desktop.click("#back")


def test_settings_paint_their_last_answer_while_the_fresh_read_runs(
  desktop: Walker,
) -> None:
  page = desktop.page
  settings = hits(page, "/api/settings")
  signing = hits(page, "/api/signing")
  desktop.goto()
  desktop.click("#settings-btn")
  page.wait_for_selector("#id-name")
  page.wait_for_function(f"!{LOADING}")
  assert (len(settings), len(signing)) == (1, 1)
  desktop.click("#settings-back")
  page.click("#settings-btn")
  painted = page.evaluate(
    f"() => ({{ name: Boolean(document.querySelector('#id-name')), loading: {LOADING} }})"
  )
  assert painted == {"name": True, "loading": False}, "the last answer paints at once"
  page.wait_for_function(f"() => !{LOADING}")
  desktop.until(lambda: len(settings) + len(signing) >= 4, "the fresh read still runs")
  assert (len(settings), len(signing)) == (2, 2), "the fresh read still runs"
  desktop.click("#settings-back")


def snapshot(job: str, count: int) -> dict[str, Any]:
  lines = [
    {"t": 1.0 + i, "text": f"2026-10-24T00:00:0{i}Z INFO line {i} of {job}"}
    for i in range(count)
  ]
  return {"id": job, "status": "done", "exit": 0, "elapsed": 1.5, "lines": lines}


def test_the_last_run_paints_before_the_server_answers(desktop: Walker) -> None:
  page = desktop.page
  answer = {"snap": snapshot("job-a", 3), "hold": False}
  calls: list[str] = []
  held: list[Any] = []

  def reply(route: Any) -> None:
    route.fulfill(
      status=200, content_type="application/json", body=json.dumps(answer["snap"])
    )

  def latest(route: Any) -> None:
    calls.append(route.request.url)
    if answer["hold"]:
      held.append(route)
    else:
      reply(route)

  page.route("**/jobs/latest", latest)
  try:
    desktop.goto()
    desktop.click(SHOP)
    page.wait_for_function(f"document.querySelectorAll('{ROWS}').length === 3")
    desktop.click("#back")
    answer["hold"] = True
    page.click(SHOP)
    page.wait_for_selector("#view-repo", state="visible")
    assert desktop.count(ROWS) == 3, "the known run paints before the answer"
    desktop.until(lambda: bool(held), "the fresh read went out")
    with page.expect_response("**/jobs/latest"):
      reply(held.pop())
    desktop.settle()
    assert desktop.count(ROWS) == 3, "the same run id adds nothing"
    assert len(calls) == 2, "the fresh read still runs"
    desktop.click("#back")
    answer.update(snap=snapshot("job-b", 5), hold=False)
    desktop.click(SHOP)
    page.wait_for_function(f"document.querySelectorAll('{ROWS}').length === 5")
    assert "job-b" in desktop.text("#log"), "another run repaints the view"
  finally:
    page.unroute("**/jobs/latest")
  desktop.click("#back")
