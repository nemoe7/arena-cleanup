"""Log rows show the browser's clock, not the server's."""

from __future__ import annotations

import json
import re
import time
import urllib.request
from collections.abc import Iterator
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from scripts.walk import DESKTOP, Demo, Walker

# a zone the server is not in, so a stamp passed through unchanged is caught
ZONE = "UTC" if time.localtime().tm_gmtoff else "Asia/Manila"
STAMPED = re.compile(r"(\d{4}-\d\d-\d\dT\S+)\s+(?:INFO|OK|WARN|ERROR|DEBUG)\s")


@pytest.fixture(scope="module")
def abroad(browser: Any, demo: Demo) -> Iterator[Walker]:
  context = browser.new_context(**DESKTOP, timezone_id=ZONE)
  yield Walker(context, demo.url)
  context.close()


def test_log_rows_show_the_browser_clock(abroad: Walker, demo: Demo) -> None:
  abroad.goto(1200)
  abroad.click(".repo-card .repo-name", 800)
  abroad.click('input[data-opt="dry_run"]', 0)
  with abroad.page.expect_request(lambda r: "/api/jobs/" in r.url) as hit:
    abroad.click("#start", 0)
  job = hit.value.url.split("/api/jobs/")[1].split("/")[0]
  abroad.wait_status("exit")

  with urllib.request.urlopen(f"{demo.url}/api/jobs/{job}", timeout=5) as resp:
    lines = json.load(resp)["lines"]
  stamps = [m.group(1) for m in map(STAMPED.match, (ln["text"] for ln in lines)) if m]
  shown = abroad.page.eval_on_selector_all(
    "#log .log-row .t", "els => els.map((e) => e.textContent)"
  )
  assert len(shown) == len(stamps) > 0
  for stamp, clock in zip(stamps, shown, strict=True):
    local = datetime.fromisoformat(stamp).astimezone(ZoneInfo(ZONE))
    assert clock == local.strftime("%H:%M:%S")
