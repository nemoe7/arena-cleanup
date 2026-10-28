"""The dashboard sort select: three orders, newest activity first by default, kept in the browser."""

from __future__ import annotations

import pytest

from tests.e2e.harness import Walker

pytestmark = pytest.mark.e2e

NAMES = "() => [...document.querySelectorAll('.repo-card .repo-name')].map((e) => e.textContent)"
REPOS = "() => fetch('/api/repos').then((r) => r.json())"
PR_RANK = {"failing": 1, "running": 2, "passing": 3, "none": 4}


def newest_tip(repo: dict) -> int:
  return max((repo.get("status") or {}).get("activity", {}).values(), default=0)


def pr_rank(repo: dict) -> int:
  status = repo.get("status") or {}
  if not status.get("ok"):
    return 0
  return min(
    (PR_RANK.get(pr["state"], 5) for pr in status.get("pr", {}).values()), default=5
  )


def choose(walker: Walker, value: str) -> None:
  walker.page.select_option("#repo-sort", value)
  walker.settle()


def test_the_default_order_is_the_newest_arena_tip_first(desktop: Walker) -> None:
  desktop.goto()
  repos = desktop.page.evaluate(REPOS)
  assert len(repos) >= 3
  assert desktop.page.input_value("#repo-sort") == "newest"
  expected = [r["name"] for r in sorted(repos, key=lambda r: -newest_tip(r))]
  assert desktop.page.evaluate(NAMES) == expected
  # the select sits beside Reload, in the title row
  select = desktop.page.eval_on_selector("#repo-sort", "e => e.getBoundingClientRect()")
  reload = desktop.page.eval_on_selector(
    "#repos-refresh", "e => e.getBoundingClientRect()"
  )
  assert select["right"] < reload["left"] <= select["right"] + 12
  assert (
    abs(select["top"] + select["height"] / 2 - reload["top"] - reload["height"] / 2) < 1
  )


def test_name_and_pr_state_orders(desktop: Walker) -> None:
  desktop.goto()
  repos = desktop.page.evaluate(REPOS)
  choose(desktop, "name")
  assert desktop.page.evaluate(NAMES) == sorted(r["name"] for r in repos)
  choose(desktop, "pr")
  names = desktop.page.evaluate(NAMES)
  ranks = [pr_rank(next(r for r in repos if r["name"] == name)) for name in names]
  assert ranks == sorted(ranks)
  assert names[0] == "billing-api", "the failing PR first"
  assert names[-1] == "docs-site", "no PR last"


def test_the_order_survives_a_reload(desktop: Walker) -> None:
  desktop.goto()
  choose(desktop, "name")
  desktop.goto()
  assert desktop.page.input_value("#repo-sort") == "name"
  names = desktop.page.evaluate(NAMES)
  assert names == sorted(names)
  choose(desktop, "newest")
