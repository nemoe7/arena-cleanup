"""The address bar keeps a shallow history: one Back leaves a sub-view."""

from __future__ import annotations

from scripts.walk import Walker


def length(walker: Walker) -> int:
  return int(walker.page.evaluate("history.length"))


def pushed(walker: Walker) -> bool:
  return bool(walker.page.evaluate("history.state && history.state.arena"))


def test_a_sub_view_is_one_entry_deep(desktop: Walker) -> None:
  desktop.goto()
  root = length(desktop)
  assert not pushed(desktop)

  desktop.click(".repo-card .repo-name")
  assert desktop.visible("#view-repo")
  assert length(desktop) == root + 1
  assert pushed(desktop)

  # a sub-view opened from a sub-view replaces the entry
  desktop.click("#settings-btn")
  assert desktop.visible("#view-settings")
  assert length(desktop) == root + 1
  assert pushed(desktop)

  # browser Back lands on the dashboard, the root entry
  desktop.page.go_back()
  desktop.page.wait_for_selector("#view-dashboard", state="visible")
  assert not pushed(desktop)


def test_the_in_app_back_pops_the_entry(desktop: Walker) -> None:
  desktop.goto()
  desktop.click(".repo-card .repo-name")
  top = length(desktop)

  desktop.click("#back")
  assert desktop.visible("#view-dashboard")
  assert not pushed(desktop)
  assert length(desktop) == top, "a pop keeps the entry ahead of it"

  # the next sub-view takes that slot instead of stacking a third entry
  desktop.click(".repo-card .repo-name")
  assert pushed(desktop)
  assert length(desktop) == top


def test_the_tab_title_names_the_page(desktop: Walker) -> None:
  desktop.goto()
  assert desktop.page.title() == "arena-cleanup"

  desktop.click(".repo-card .repo-name")
  name = desktop.text("#repo-title").strip()
  assert name
  assert desktop.page.title() == f"arena-cleanup | {name}"

  desktop.click("#settings-btn")
  assert desktop.page.title() == "arena-cleanup | Settings"

  # in-app Back returns to the repo, and the title follows
  desktop.click("#settings-back")
  assert desktop.visible("#view-repo")
  assert desktop.page.title() == f"arena-cleanup | {name}"

  # browser Back pops to the dashboard, the root entry
  desktop.page.go_back()
  desktop.page.wait_for_selector("#view-dashboard", state="visible")
  desktop.page.wait_for_function("document.title === 'arena-cleanup'")
