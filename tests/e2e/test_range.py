"""The timeout slider follows the nuu range recipe.

A tick per stop sits under the track, and the two ends carry their values. The
readout names the chosen stop (docs/design.md).
"""

from __future__ import annotations

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e


def open_repo(walker: Walker) -> None:
  walker.goto(1200)
  walker.click(".repo-card .repo-name", 800)


TICKS = """() => {
  const input = document.querySelector('#timeout');
  const list = document.getElementById(input.getAttribute('list'));
  const ends = [...document.querySelectorAll('#opt-timeout .range-ends span')].map((s) => s.textContent);
  const stops = Number(input.max) - Number(input.min) + 1;
  return { ticks: list ? list.options.length : 0, stops, ends, readout: document.querySelector('#timeout-out').value };
}"""
LAYOUT = """() => {
  const track = document.querySelector('#timeout').getBoundingClientRect();
  const ends = document.querySelector('#opt-timeout .range-ends').getBoundingClientRect();
  const out = document.querySelector('#timeout-out').getBoundingClientRect();
  return { endsBelow: ends.top >= track.bottom, outOnTrack: out.top < track.bottom && out.bottom > track.top };
}"""


def test_a_tick_per_stop_and_named_ends(desktop: Walker) -> None:
  open_repo(desktop)
  got = desktop.page.evaluate(TICKS)
  assert got["ticks"] == got["stops"], "one tick per stop"
  assert got["ends"][0] == "0" and got["ends"][-1].startswith("120"), (
    "the ends name their values"
  )
  assert got["readout"].endswith("min"), "the readout names the stop"
  layout = desktop.page.evaluate(LAYOUT)
  assert layout["endsBelow"], "the ends sit under the track"
  assert layout["outOnTrack"], "the readout stays level with the track"


def test_the_ends_sit_under_the_track_on_a_phone(phone: Walker) -> None:
  open_repo(phone)
  layout = phone.page.evaluate(LAYOUT)
  assert layout["endsBelow"] and layout["outOnTrack"]
