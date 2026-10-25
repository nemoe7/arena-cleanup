"""The repo view shows the repo it names, with a status and a commit list as fresh as the dashboard's.

A slow status answer stays with its repo. A deleted branch takes its
commits off the list. The list tick refreshes the sidebar. A return from
Settings reads again, and Clean & Push waits for the first fresh status.
"""

from __future__ import annotations

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

CARD = ".repo-card:has-text('{name}') .repo-name"
ROWS = "#side-top .arena-item"
BRANCHES = "els => els.map((e) => e.dataset.branch)"
# the status read of one repo answers 2.5 s late, and the page's own fetch does the rest
DELAY = """(id) => {
  const orig = window.fetch;
  window.__fetch = orig;
  window.fetch = (u, i) => (typeof u === 'string' && u.endsWith('/api/repos/' + id))
    ? new Promise((r) => setTimeout(() => r(orig(u, i)), 2500))
    : orig(u, i);
}"""
RESTORE = "() => { if (window.__fetch) window.fetch = window.__fetch; }"


def repo_id(walker: Walker, name: str) -> str:
  repos = walker.page.request.get(f"{walker.url}/api/repos").json()
  return next(r["id"] for r in repos if r["name"] == name)


def test_a_slow_status_answer_stays_with_its_repo(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto(1200)
  page.evaluate(DELAY, repo_id(desktop, "billing-api"))
  try:
    page.click(CARD.format(name="billing-api"))
    page.wait_for_timeout(250)
    page.click("#back")
    page.wait_for_selector(CARD.format(name="shop-web"))
    page.wait_for_timeout(150)
    page.click(CARD.format(name="shop-web"))
    page.wait_for_timeout(3200)
    assert page.inner_text("#repo-title") == "shop-web", (
      "the late answer repainted the view"
    )
    assert page.eval_on_selector_all(f"{ROWS} .select", BRANCHES) == [
      "arena/3f7c2e1a-shop-web"
    ]
  finally:
    page.evaluate(RESTORE)
