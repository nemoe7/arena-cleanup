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


def subjects(walker: Walker, rid: str, ref: str) -> list[str]:
  res = walker.page.request.get(
    f"{walker.url}/api/repos/{rid}/commits?limit=3&ref={ref}"
  )
  return [c["subject"] for c in res.json()["commits"]]


def test_a_deleted_branch_takes_its_commits_off_the_list(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto(1200)
  rid = repo_id(desktop, "data-pipeline")
  desktop.click(CARD.format(name="data-pipeline"), 800)
  page.wait_for_selector(ROWS)
  desktop.click(f"{ROWS}:not(.selected) .select", 700)
  chosen = page.get_attribute(f"{ROWS}.selected .select", "data-branch")
  other = page.get_attribute(f"{ROWS}:not(.selected) .select", "data-branch")
  assert (
    page.inner_text("#commits .commit .subject") == subjects(desktop, rid, chosen)[0]
  )
  # other tests need this branch on the server, so this route answers its delete
  page.route(
    "**/api/repos/*/arena/delete",
    lambda route: route.fulfill(status=200, content_type="application/json", body="{}"),
  )
  try:
    desktop.click(f"{ROWS}.selected .arena-del", 300)
    desktop.click("#confirm-go", 0)
    want = subjects(desktop, rid, other)[0]
    page.wait_for_function(
      f"document.querySelector('#commits .commit .subject').textContent === {want!r}"
    )
  finally:
    page.unroute_all(behavior="ignoreErrors")


def test_the_list_tick_refreshes_the_sidebar(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto(1200)
  desktop.click(CARD.format(name="docs-site"), 800)
  assert "clean" in page.inner_text("#side-top")

  def dirty(route):  # a list read that says the clone has three changes
    body = route.fetch().json()
    for repo in body:
      if repo["name"] == "docs-site":
        repo["status"]["dirty"] = 3
    route.fulfill(json=body)

  page.route(lambda url: url.endswith("/api/repos"), dirty)
  try:
    page.evaluate("() => window.dispatchEvent(new Event('online'))")
    page.wait_for_function(
      "() => document.querySelector('#side-top').innerText.includes('3 uncommitted')"
    )
  finally:
    page.unroute_all(behavior="ignoreErrors")


def test_a_return_from_settings_reads_the_status_again(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto(1200)
  rid = repo_id(desktop, "docs-site")
  desktop.click(CARD.format(name="docs-site"), 800)
  desktop.click("#settings-btn", 400)
  with page.expect_request(lambda r: r.url.endswith(f"/api/repos/{rid}")):
    desktop.click("#settings-back", 0)
  assert page.inner_text("#repo-title") == "docs-site"


def test_clean_and_push_waits_for_the_first_fresh_status(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto(1200)
  page.evaluate(DELAY, repo_id(desktop, "shop-web"))
  try:
    page.click(CARD.format(name="shop-web"))
    page.wait_for_timeout(300)
    assert page.eval_on_selector("#start", "e => e.disabled")
    assert page.get_attribute("#start", "title") == "reading the branch state"
    page.wait_for_function(
      "() => !document.querySelector('#start').disabled", timeout=5000
    )
    assert page.get_attribute("#start", "title").startswith("Runs:")
  finally:
    page.evaluate(RESTORE)
