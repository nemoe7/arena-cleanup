"""The options card: phone tap targets and the arena branch labels."""

from __future__ import annotations

from scripts.walk import Walker

TAP_TARGET_PX = 44
FIELD_TEXT_PX = 16.0
BOX = "e => { const b = e.getBoundingClientRect(); return [b.width, b.height]; }"


def test_the_path_field_and_browse_are_tap_targets(phone: Walker) -> None:
  phone.goto(400)
  phone.click(".repo-card", 800)
  width, height = phone.page.eval_on_selector("#pathin", BOX)
  assert height >= TAP_TARGET_PX
  assert width > TAP_TARGET_PX
  size = phone.page.eval_on_selector(
    "#pathin", "e => parseFloat(getComputedStyle(e).fontSize)"
  )
  assert size == FIELD_TEXT_PX
  width, height = phone.page.eval_on_selector("#browse", BOX)
  assert min(width, height) >= TAP_TARGET_PX


def test_the_arena_option_shows_the_branch_and_the_day(desktop: Walker) -> None:
  desktop.goto(1200)
  desktop.click(".repo-card:has-text('data-pipeline')", 800)
  assert desktop.visible("#opt-arena")
  options = desktop.page.eval_on_selector_all(
    "#arena option", "els => els.map((o) => [o.value, o.textContent, o.title])"
  )
  assert len(options) >= 2
  for value, label, title in options:
    assert label.startswith(f"{value} · ") and ":" not in label, label
    assert title.startswith(value) and ":" in title, title


def test_the_option_rows_share_their_lines(desktop: Walker) -> None:
  desktop.goto(1200)
  desktop.click(".repo-card", 800)
  edges = "e => { const b = e.getBoundingClientRect(); return [b.top, b.bottom]; }"
  rows = {
    name: desktop.page.eval_on_selector(f"#{name}", edges)
    for name in ("opt-branch", "opt-paths", "opt-timeout", "checks")
  }
  assert rows["opt-timeout"] == rows["opt-branch"]
  assert rows["checks"] == rows["opt-paths"]
  assert rows["opt-paths"][0] == rows["opt-branch"][1]


POINTER_TARGET_PX = 24


def test_the_option_controls_are_pointer_targets(desktop: Walker) -> None:
  desktop.goto(1200)
  desktop.click(".repo-card", 800)
  desktop.click("#browse", 600)
  desktop.click(".tree-select", 300)
  sizes = desktop.page.eval_on_selector_all(
    "#browse, .chip-x button, .tree-select, .check, .slider",
    "els => els.map((e) => { const b = e.getBoundingClientRect(); return [e.className, b.width, b.height]; })",
  )
  assert len(sizes) >= 5
  for name, width, height in sizes:
    assert min(width, height) >= POINTER_TARGET_PX, (name, width, height)
