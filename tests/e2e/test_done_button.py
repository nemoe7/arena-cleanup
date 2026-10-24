"""Clean & Push greys when a clean has nothing to do.

From the run end until the branch state answers, the button reads `reading
the branch state`. An arena branch with nothing ahead keeps it grey, and
commits ahead re-arm it.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from scripts.walk import Walker
from tests.e2e.test_phase_modals import RUN

pytestmark = pytest.mark.e2e

BUTTONS = """() => ['start', 'start-mobile'].map((id) => {
  const b = document.getElementById(id);
  return { disabled: b.disabled, title: b.title };
})"""
REPO = "shop-web"
BRANCH = "arena/session-3"
LIST = "**/api/repos"
FETCH = "**/api/fetch"
ONE = "**/api/repos/*"
LATEST = "**/api/repos/*/jobs/latest"
JOB = "**/api/jobs/fake"
EVENTS = "**/api/jobs/fake/events"


def zero_ahead(route: Any) -> None:
  """Answer the real repo data, with BRANCH at nothing ahead."""
  res = route.fetch()
  body = res.json()
  for repo in body if isinstance(body, list) else [body]:
    ahead = (repo.get("status") or {}).get("ahead") or {}
    if BRANCH in ahead:
      ahead[BRANCH] = 0
  route.fulfill(response=res, body=json.dumps(body))


def open_repo(walker: Walker, name: str = REPO) -> None:
  walker.goto(1200)
  walker.click(f".repo-card:has-text('{name}') .repo-name", 800)


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_nothing_ahead_greys_the_button(
  request: pytest.FixtureRequest, width: str
) -> None:
  walker: Walker = request.getfixturevalue(width)
  page = walker.page
  for pattern in (LIST, FETCH, ONE):
    page.route(pattern, zero_ahead)
  try:
    open_repo(walker)
    for btn in page.evaluate(BUTTONS):
      assert btn["disabled"] is True, btn
      assert btn["title"] == f"nothing to clean on {BRANCH}"
  finally:
    for pattern in (LIST, FETCH, ONE):
      page.unroute(pattern)
  open_repo(walker)
  for btn in page.evaluate(BUTTONS):
    assert btn["disabled"] is False, "commits ahead keep the button live"
    assert btn["title"].startswith("Runs:")


def snap(status: str) -> str:
  lines = RUN[:8]
  return json.dumps(
    {
      "id": "fake",
      "status": status,
      "exit": None if status == "running" else 0,
      "cancelled": False,
      "elapsed": float(len(lines)),
      "lines": [
        {
          "t": 1_700_000_000 + i,
          "text": f"2026-10-24T10:00:{i:02d}+0000 {level} {text}",
        }
        for i, (level, text) in enumerate(lines)
      ],
    }
  )


def test_the_button_waits_for_the_branch_state_after_a_run(desktop: Walker) -> None:
  page = desktop.page
  held: list[Any] = []

  def fulfil(body: str) -> Any:
    return lambda r: r.fulfill(status=200, content_type="application/json", body=body)

  page.route(LATEST, fulfil(snap("running")))
  page.route(EVENTS, lambda r: r.abort())
  page.route(JOB, fulfil(snap("done")))
  page.route(ONE, lambda r: held.append(r))
  try:
    open_repo(desktop, "infra-tools")
    page.wait_for_function("document.getElementById('start').dataset.state === 'idle'")
    for btn in page.evaluate(BUTTONS):
      assert btn["disabled"] is True, "grey from the run end"
      assert btn["title"] == "reading the branch state"
  finally:
    for r in held:
      r.continue_()
    page.unroute(ONE)
    page.unroute(LATEST)
    page.unroute(EVENTS)
    page.unroute(JOB)
  page.wait_for_function("!document.getElementById('start').disabled")
  assert page.evaluate(BUTTONS)[0]["title"].startswith("Runs:"), (
    "commits ahead re-arm it"
  )
