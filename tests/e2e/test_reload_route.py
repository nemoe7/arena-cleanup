"""A reload off the dashboard paints the named screen first.

The boot sequence loads the environment, the sign-in state, and the repos
before it applies the hash. The hash picks the visible view before that
work starts, so the dashboard never shows as an interstitial.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.walk import Demo, Walker

pytestmark = pytest.mark.e2e

VIEWS = """() => Object.fromEntries(['dashboard', 'repo', 'settings']
  .map((name) => [name, !document.getElementById('view-' + name).hidden]))"""


def repo_hash(demo: Demo) -> str:
  repos = demo.api("/api/repos")
  return "#/repo/" + repos[0]["id"]


def wait_held(page: Any, held: list[Any]) -> None:
  """The route event lands after the navigation returns, so give it a moment."""
  for _ in range(40):
    if held:
      return
    page.wait_for_timeout(50)
  raise AssertionError("the boot sequence asked for the environment")


@pytest.mark.parametrize(
  ("route", "settled", "view"),
  [
    ("#/settings", "#card-identity", "settings"),
    ("repo", "#view-repo .commit", "repo"),
  ],
)
def test_a_reload_shows_the_named_view_before_the_status_loads(
  desktop: Walker, demo: Demo, route: str, settled: str, view: str
) -> None:
  page = desktop.page
  target = repo_hash(demo) if route == "repo" else route
  held: list[Any] = []
  # a hash change inside the open page is no reload: leave the page first
  page.goto("about:blank")
  page.route("**/api/env", lambda r: held.append(r))
  try:
    page.goto(f"{desktop.url}/{target}", wait_until="domcontentloaded")
    wait_held(page, held)
    assert page.evaluate(VIEWS) == {
      "dashboard": False,
      "repo": view == "repo",
      "settings": view == "settings",
    }
  finally:
    for r in held:
      r.continue_()
    page.unroute("**/api/env")
  page.wait_for_selector(settled)
  assert page.evaluate(VIEWS)[view] is True
  assert page.evaluate(VIEWS)["dashboard"] is False


def test_a_reload_at_the_root_keeps_the_dashboard(desktop: Walker) -> None:
  desktop.page.goto("about:blank")
  desktop.page.goto(f"{desktop.url}/", wait_until="domcontentloaded")
  assert desktop.page.evaluate(VIEWS) == {
    "dashboard": True,
    "repo": False,
    "settings": False,
  }
  desktop.page.wait_for_selector(".repo-card")
