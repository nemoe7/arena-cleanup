"""A dashboard row shows a clean in flight on its repo.

The server flags a repo with a live job. Its Clean & Push button turns into
Running: disabled, an amber pulsing dot, and the same box. The reason is
its title, and the row carries aria-busy. The return from the repo view reads
the list again, so the row shows a run started there (docs/design.md).
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest

from scripts.walk import Demo, Walker

pytestmark = pytest.mark.e2e

REPO = "shop-web"
CARD = f".repo-card:has-text('{REPO}')"
ROW = """(card) => {
  const btn = card.querySelector('button.clean');
  const slot = btn.querySelector('.busy .ico-svg');
  const glyph = getComputedStyle(slot);
  const dot = slot.querySelector('.dot');
  const warn = getComputedStyle(document.documentElement).getPropertyValue('--warn').trim();
  return { busy: card.getAttribute('aria-busy'), pills: card.querySelectorAll('.repo-meta .pill').length,
    running: btn.classList.contains('running'), label: btn.innerText.trim(),
    disabled: btn.disabled, title: btn.title, amber: glyph.color === warn || glyph.color === hex(warn),
    dot: Boolean(dot) && !slot.querySelector('svg'),
    pulses: dot ? getComputedStyle(dot).animationName === 'pulse' : false,
    box: [btn.offsetWidth, btn.offsetHeight], pair: pair() };
  // the visible pair, dot box to label end, sits on the button centre with an 8 px
  // gap. The box stands still while the pulse scales the dot inside it
  function pair() {
    const busy = btn.querySelector('.busy');
    const range = document.createRange();
    range.selectNodeContents([...busy.childNodes].find((n) => n.nodeType === 3));
    const text = range.getBoundingClientRect();
    const d = slot.getBoundingClientRect();
    const b = btn.getBoundingClientRect();
    const skew = (d.left + text.right) / 2 - (b.left + b.width / 2);
    return [Math.round(text.left - d.right), Math.abs(skew) <= 1];
  }
  function hex(c) {
    const m = /^#([0-9a-f]{6})$/i.exec(c);
    return m ? `rgb(${[0, 2, 4].map((i) => parseInt(m[1].slice(i, i + 2), 16)).join(', ')})` : c;
  }
}"""
REASON = "a clean is running on this repo"


def test_a_live_job_marks_its_row(desktop: Walker) -> None:
  page = desktop.page
  reads: list[Any] = []

  def flag(route: Any) -> None:
    reply = route.fetch()
    repos = reply.json()
    for repo in repos:
      repo["running"] = repo["name"] == REPO
    reads.append(len(repos))
    route.fulfill(response=reply, body=json.dumps(repos))

  # first paint comes from the fetch, later reads from the list
  page.route("**/api/fetch", flag)
  page.route("**/api/repos", flag)
  try:
    desktop.goto(1200)
    page.wait_for_selector(f"{CARD} button.clean.running")
    row = page.eval_on_selector(CARD, ROW)
    other = page.eval_on_selector(".repo-card:has-text('billing-api')", ROW)
    assert row == {
      "busy": "true",
      "pills": 1,
      "running": True,
      "label": "Running",
      "disabled": True,
      "title": REASON,
      "amber": True,
      "dot": True,
      "pulses": True,
      "box": other["box"],
      "pair": [8, True],
    }, "the button carries the run, no pill, an idle box, and a centred pair"
    assert other["busy"] is None and other["label"] == "Clean & Push", "one row alone"
    assert other["pulses"] is False
    # repo view and back: the return reads the statuses once more
    before = len(reads)
    desktop.click(f"{CARD} .repo-name", 600)
    desktop.click("#back", 600)
    page.wait_for_selector(f"{CARD} button.clean.running")
    deadline = time.monotonic() + 5
    while len(reads) < before + 1 and time.monotonic() < deadline:
      page.wait_for_timeout(100)
    assert len(reads) == before + 1, "one fresh read on return"
  finally:
    page.unroute("**/api/repos")
    page.unroute("**/api/fetch")
  desktop.goto(1200)
  page.wait_for_selector(CARD)
  assert page.eval_on_selector(CARD, ROW)["running"] is False, (
    "a plain reload clears it"
  )


def test_a_run_started_here_marks_its_row_before_the_list_answers(
  desktop: Walker, demo: Demo, signing: None
) -> None:
  """Back from the repo view finds the card grey, even on a stale list read."""
  page = desktop.page
  card = ".repo-card:has-text('docs-site')"
  reads: list[int] = []

  def stale(route: Any) -> None:
    # the list as it stood before the run started
    reply = route.fetch()
    repos = reply.json()
    for entry in repos:
      entry["running"] = False
    reads.append(len(repos))
    route.fulfill(response=reply, body=json.dumps(repos))

  desktop.goto(1200)
  desktop.click(f"{card} .repo-name", 800)
  demo.slow_checks(True)
  page.route("**/api/repos", stale)
  try:
    box = 'input[data-opt="dry_run"]'
    if page.is_checked(box):
      desktop.click(box, 150)
    desktop.click("#start", 0)
    assert desktop.wait_status("running") == "running"
    assert page.eval_on_selector(card, ROW)["running"] is True, (
      "the card behind the repo view is marked at once"
    )
    desktop.click("#back", 600)
    assert page.eval_on_selector(card, ROW)["running"] is True, "Back finds it grey"
    deadline = time.monotonic() + 5
    while not reads and time.monotonic() < deadline:
      page.wait_for_timeout(100)
    assert reads, "the return reads the list"
    page.wait_for_timeout(200)
    assert page.eval_on_selector(card, ROW)["running"] is True, (
      "a read from before the start cannot undo it"
    )
    desktop.click(f"{card} .repo-name", 800)
    desktop.click("#start", 0)
    assert "cancelled" in desktop.wait_status("cancelled")
  finally:
    page.unroute("**/api/repos")
    demo.slow_checks(False)
