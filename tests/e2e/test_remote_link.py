"""The remote row of the repo view links a GitHub remote as owner/repo.

An https or ssh GitHub remote renders as the GitHub mark and `owner/repo`.
The link opens the repo page in a new tab. Any other remote stays plain text
(docs/design.md).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.e2e.harness import Walker

pytestmark = pytest.mark.e2e

REPO = "shop-web"
OTHER = "billing-api"
CARD = ".repo-card:has-text('{name}') .repo-name"
ROUTES = ("**/api/fetch", "**/api/repos", "**/api/repos/*")
LINK = (
  "(a) => ({ href: a.href, text: a.textContent, target: a.target, rel: a.rel,"
  " title: a.title, mark: a.querySelectorAll('svg path').length })"
)


def patch(route: Any, name: str, status: dict[str, Any]) -> None:
  """Answer with the real payload, with `status` merged into repo `name`."""
  reply = route.fetch()
  data = reply.json()
  for repo in data if isinstance(data, list) else [data]:
    if repo.get("name") == name:
      repo["status"].update(status)
  route.fulfill(response=reply, body=json.dumps(data))


def test_a_github_remote_links_owner_and_repo(desktop: Walker) -> None:
  # the demo origins answer to https://github.com/demo/<name>
  page = desktop.page
  desktop.goto()
  desktop.click(CARD.format(name=REPO))
  link = page.eval_on_selector("#side-top .kv dd .remote-link", LINK)
  assert link == {
    "href": f"https://github.com/demo/{REPO}",
    "text": f"demo/{REPO}",
    "target": "_blank",
    "rel": "noopener",
    "title": f"Open demo/{REPO} on GitHub",
    "mark": 1,
  }
  desktop.click("#back")
  # any other remote keeps the plain text
  local = f"/srv/git/{OTHER}.git"
  for pattern in ROUTES:
    page.route(pattern, lambda route: patch(route, OTHER, {"remote": local}))
  try:
    desktop.click(CARD.format(name=OTHER))
    # the view paints the cached card first, then the patched read lands
    page.wait_for_function(
      "(local) => document.querySelector('#side-top').innerText.includes(local)",
      arg=local,
    )
    assert page.query_selector("#side-top .kv dd .remote-link") is None
    cells = page.eval_on_selector_all(
      "#side-top .kv dd", "(ds) => ds.map((d) => d.textContent)"
    )
    assert local in cells, cells
  finally:
    for pattern in ROUTES:
      page.unroute(pattern)
