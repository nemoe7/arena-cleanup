"""List edits show before the reply: the row leaves or arrives at once, a failure undoes it."""

from __future__ import annotations

import json
import time
from typing import Any

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

BRANCH = "arena/3f7c2e1a-shop-web"
ROW = f".arena-item:has(.row-btn[data-branch='{BRANCH}'])"
CARD = ".repo-card:has-text('docs-site')"
PENDING = ".repo-card.pending"
SETTLE = 150


def wait_for(held: list[Any], page: Any) -> Any:
  deadline = time.monotonic() + 5
  while not held and time.monotonic() < deadline:
    page.wait_for_timeout(50)
  assert held, "the page sent the request"
  return held[0]


def fail(route: Any) -> None:
  route.fulfill(
    status=500,
    content_type="application/json",
    body=json.dumps({"error": "origin refused"}),
  )


def test_the_arena_row_leaves_before_the_reply_and_returns_on_failure(
  desktop: Walker,
) -> None:
  page = desktop.page
  held: list[Any] = []
  page.route("**/api/repos/*/arena/delete", lambda route: held.append(route))
  try:
    desktop.goto(1200)
    desktop.click(".repo-card:has-text('shop-web') .repo-name", 800)
    assert desktop.count(ROW) == 1
    desktop.click(f"{ROW} .arena-del", 300)
    desktop.click("#confirm-go", SETTLE)
    route = wait_for(held, page)
    assert desktop.count_settled(ROW, 0) == 0, "the row left before the server answered"
    fail(route)
    assert desktop.count_settled(ROW, 1) == 1, "a refused delete puts the row back"
    assert "origin refused" in desktop.text("#toast")
  finally:
    page.unroute("**/api/repos/*/arena/delete")


SHOP_ROW = f".repo-card:has-text('shop-web') .arena-row:has(.bname[title='{BRANCH}'])"


def test_a_reload_during_the_delete_keeps_the_branch_off_the_card(
  desktop: Walker,
) -> None:
  page = desktop.page
  held: list[Any] = []
  page.route("**/api/repos/*/arena/delete", lambda route: held.append(route))
  try:
    desktop.goto(1200)
    desktop.click(".repo-card:has-text('shop-web') .repo-name", 800)
    desktop.click(f"{ROW} .arena-del", 300)
    desktop.click("#confirm-go", SETTLE)
    route = wait_for(held, page)
    # Back reloads the list from a server that still has the branch
    desktop.click("#back", 800)
    assert desktop.count(".repo-card") > 0
    assert desktop.count_settled(SHOP_ROW, 0) == 0, (
      "a reload keeps the branch off the card"
    )
    fail(route)
    assert desktop.count_settled(SHOP_ROW, 1) == 1, "a refused delete puts it back"
  finally:
    page.unroute("**/api/repos/*/arena/delete")


def test_the_card_leaves_before_the_reply_and_returns_on_failure(
  desktop: Walker,
) -> None:
  page = desktop.page
  held: list[Any] = []
  page.route("**/api/repos/*/remove", lambda route: held.append(route))
  try:
    desktop.goto(1200)
    cards = desktop.count(".repo-card")
    desktop.click(f"{CARD} .rm", 100)
    desktop.click(f"{CARD} .rm", SETTLE)
    route = wait_for(held, page)
    assert desktop.count_settled(CARD, 0) == 0, (
      "the card left before the server answered"
    )
    assert desktop.count(".repo-card") == cards - 1
    fail(route)
    assert desktop.count_settled(CARD, 1) == 1, "a refused remove puts the card back"
  finally:
    page.unroute("**/api/repos/*/remove")


def test_the_add_bar_shows_a_pending_card_before_the_clone_answers(
  desktop: Walker,
) -> None:
  page = desktop.page
  held: list[Any] = []

  def hold_posts(route: Any) -> None:
    if route.request.method == "POST":
      held.append(route)
    else:
      route.continue_()

  page.route("**/api/repos", hold_posts)
  try:
    desktop.goto(1200)
    cards = desktop.count(".repo-card")
    page.fill("#add-source", "https://github.com/acme/new-repo.git")
    desktop.click("#add-btn", SETTLE)
    route = wait_for(held, page)
    assert desktop.count(PENDING) == 1, "a pending card shows before the clone answers"
    assert "new-repo" in desktop.text(PENDING)
    assert "cloning" in desktop.text(PENDING)
    first = page.eval_on_selector(".repo-card", "e => e.className")
    assert "pending" in first, "the pending card leads the grid"
    assert desktop.count(".repo-card") == cards + 1
    page.click("#repos-refresh")
    page.wait_for_timeout(SETTLE * 4)
    assert desktop.count(PENDING) == 1, "a reload of the list keeps the pending card"
    fail(route)
    page.wait_for_timeout(SETTLE)
    assert desktop.count(PENDING) == 0, "a refused clone takes the pending card away"
    assert desktop.count(".repo-card") == cards
  finally:
    page.unroute("**/api/repos")


def test_a_clone_refused_during_a_reload_leaves_no_card_behind(desktop: Walker) -> None:
  page = desktop.page
  posts: list[Any] = []
  fetches: list[Any] = []

  def hold_posts(route: Any) -> None:
    if route.request.method == "POST":
      posts.append(route)
    else:
      route.continue_()

  page.route("**/api/repos", hold_posts)
  try:
    desktop.goto(1200)
    page.route("**/api/fetch", lambda route: fetches.append(route))
    cards = desktop.count(".repo-card")
    page.fill("#add-source", "https://github.com/acme/late-repo.git")
    desktop.click("#add-btn", SETTLE)
    clone = wait_for(posts, page)
    page.click("#repos-refresh")
    reload = wait_for(fetches, page)
    fail(clone)
    page.wait_for_timeout(SETTLE)
    assert desktop.count(PENDING) == 0
    fresh = page.evaluate("fetch('/api/repos').then((r) => r.text())")
    reload.fulfill(status=200, content_type="application/json", body=fresh)
    page.wait_for_timeout(SETTLE)
    assert desktop.count(PENDING) == 0, (
      "the reload in flight does not bring the refused clone back"
    )
    assert desktop.count(".repo-card") == cards
  finally:
    page.unroute("**/api/repos")
    page.unroute("**/api/fetch")
