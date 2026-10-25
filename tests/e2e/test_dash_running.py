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

from scripts.walk import Walker

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
    box: [btn.offsetWidth, btn.offsetHeight] };
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
    }, "the button carries the run, no pill, and the same box as an idle one"
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
