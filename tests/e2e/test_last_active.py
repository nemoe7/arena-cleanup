"""A dashboard card names the time since the repo was last active.

The stamp is the newest of three: a check completion, an arena tip commit, and
a PR edit. It reads in the nuu relative form, `30min ago`, and its title names
the full form with the source (docs/design.md).
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

SHOP = ".repo-card:has-text('shop-web')"
DOCS = ".repo-card:has-text('docs-site')"
COMPACT = re.compile(r"^(now|\d+(min|h|d|wk|mo|yr) ago)$")
HOUR = 3600


def iso(secs_ago: float) -> str:
  return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - secs_ago))


def stamp(route: Any) -> None:
  """shop-web: tip 3 h ago, PR edit 2 h ago, check 30 min ago. docs-site: tip 2 days ago, no PR."""
  reply = route.fetch()
  repos = reply.json()
  for repo in repos:
    status = repo.get("status") or {}
    if not status.get("arena"):
      continue
    branch = status["arena"][0]
    if repo["name"] == "shop-web":
      status["activity"] = {branch: int(time.time() - 3 * HOUR)}
      status["pr"][branch]["updated"] = iso(2 * HOUR)
      status["pr"][branch]["checked"] = iso(30 * 60)
    if repo["name"] == "docs-site":
      status["activity"] = {branch: int(time.time() - 2 * 24 * HOUR)}
      status["pr"] = {}
  route.fulfill(response=reply, body=json.dumps(repos))


def test_the_newest_of_check_tip_and_edit_is_the_stamp(desktop: Walker) -> None:
  page = desktop.page
  page.route("**/api/repos", stamp)
  page.route("**/api/fetch", stamp)
  try:
    desktop.goto(1200)
    page.wait_for_selector(f"{SHOP} .repo-since")
    shop = page.eval_on_selector(f"{SHOP} .repo-since", "e => [e.textContent, e.title]")
    assert shop == ["30min ago", "Last active 30 minutes ago: PR #142 check"]
    docs = page.eval_on_selector(f"{DOCS} .repo-since", "e => [e.textContent, e.title]")
    assert docs == ["2d ago", "Last active 2 days ago: arena tip commit"]
    # one line: name first, stamp after it
    name = page.eval_on_selector(
      f"{SHOP} .repo-name", "e => e.getBoundingClientRect().toJSON()"
    )
    since = page.eval_on_selector(
      f"{SHOP} .repo-since", "e => e.getBoundingClientRect().toJSON()"
    )
    assert since["left"] >= name["right"]
    assert since["bottom"] <= name["bottom"] + 1 and since["top"] >= name["top"] - 1
  finally:
    page.unroute_all(behavior="ignoreErrors")


def test_every_ready_card_carries_a_compact_stamp(desktop: Walker) -> None:
  desktop.goto(1200)
  page = desktop.page
  page.wait_for_selector(".repo-card .repo-since")
  stamps = page.eval_on_selector_all(
    ".repo-card:not(.pending) .repo-since", "els => els.map((e) => e.textContent)"
  )
  assert stamps and all(COMPACT.match(s) for s in stamps), stamps
