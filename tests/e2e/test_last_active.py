"""A dashboard card names the time since the repo was last active.

The stamp is the newest of three: a check completion, an arena tip commit, and
a PR edit. Without an arena branch the default tip commit keeps it. A desktop
reads the full form, `30 minutes ago`, and a phone the compact one, `30min
ago`. The title names the full form with the source (docs/design.md).
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
FULL = re.compile(
  r"^(just now|yesterday|last (week|month|year)|an? (minute|hour) ago"
  r"|\d+ (minutes|hours|days|weeks|months|years) ago)$"
)
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
    desktop.goto()
    page.wait_for_selector(f"{SHOP} .repo-since")
    shop = page.eval_on_selector(f"{SHOP} .repo-since", "e => [e.innerText, e.title]")
    assert shop == ["30 minutes ago", "Last active 30 minutes ago: PR #142 check"]
    docs = page.eval_on_selector(f"{DOCS} .repo-since", "e => [e.innerText, e.title]")
    assert docs == ["2 days ago", "Last active 2 days ago: arena tip commit"]
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


def no_arena(route: Any) -> None:
  """docs-site: no arena branch, no PR, the main tip 5 days ago."""
  reply = route.fetch()
  repos = reply.json()
  for repo in repos:
    if repo["name"] == "docs-site":
      status = repo["status"]
      status.update(arena=[], activity={}, pr={}, ahead={}, tips={})
      status["default_at"] = int(time.time() - 5 * 24 * HOUR)
  route.fulfill(response=reply, body=json.dumps(repos))


def test_a_repo_without_an_arena_branch_keeps_its_stamp(desktop: Walker) -> None:
  page = desktop.page
  page.route("**/api/repos", no_arena)
  page.route("**/api/fetch", no_arena)
  try:
    desktop.goto()
    page.wait_for_selector(f"{DOCS} .arena-row:has-text('no arena/* branches')")
    docs = page.eval_on_selector(f"{DOCS} .repo-since", "e => [e.innerText, e.title]")
    assert docs == ["5 days ago", "Last active 5 days ago: main tip commit"]
  finally:
    page.unroute_all(behavior="ignoreErrors")


def test_every_ready_card_carries_a_full_stamp_on_a_desktop(desktop: Walker) -> None:
  desktop.goto()
  page = desktop.page
  page.wait_for_selector(".repo-card .repo-since")
  stamps = page.eval_on_selector_all(
    ".repo-card:not(.pending) .repo-since", "els => els.map((e) => e.innerText)"
  )
  assert stamps and all(FULL.match(s) for s in stamps), stamps
  face = page.eval_on_selector(".repo-since", "e => getComputedStyle(e).fontFamily")
  assert "Inter" in face and "Monaspace" not in face, "the UI face, not the mono one"


def test_every_ready_card_carries_a_compact_stamp_on_a_phone(phone: Walker) -> None:
  phone.goto()
  page = phone.page
  page.wait_for_selector(".repo-card .repo-since")
  stamps = page.eval_on_selector_all(
    ".repo-card:not(.pending) .repo-since", "els => els.map((e) => e.innerText)"
  )
  assert stamps and all(COMPACT.match(s) for s in stamps), stamps
