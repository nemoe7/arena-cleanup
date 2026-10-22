"""A demo instance plus a real Chromium for the browser tests.

The page objects live in `scripts/walk.py`, the hand-run walk. Set
`E2E_CHROMIUM` to a Chromium binary to run without `playwright install`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest

from scripts.walk import DESKTOP, PHONE_DEVICE, Demo, Walker, launch_browser


@pytest.fixture(scope="session")
def demo(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Demo]:
  server = Demo(tmp_path_factory.mktemp("demo"))
  yield server
  server.stop()


@pytest.fixture(scope="session")
def playwright() -> Iterator[Any]:
  sync_api = pytest.importorskip(
    "playwright.sync_api", reason="playwright is not installed (uv sync --group qa)"
  )
  with sync_api.sync_playwright() as instance:
    yield instance


@pytest.fixture(scope="session")
def browser(playwright: Any) -> Iterator[Any]:
  try:
    instance = launch_browser(playwright, os.environ.get("E2E_CHROMIUM"))
  except Exception as exc:
    pytest.skip(f"no Chromium for Playwright: {str(exc).splitlines()[0]}")
  yield instance
  instance.close()


@pytest.fixture(scope="module")
def desktop(browser: Any, demo: Demo) -> Iterator[Walker]:
  context = browser.new_context(**DESKTOP)
  yield Walker(context, demo.url)
  context.close()


@pytest.fixture(scope="module")
def phone(browser: Any, playwright: Any, demo: Demo) -> Iterator[Walker]:
  context = browser.new_context(**playwright.devices[PHONE_DEVICE])
  yield Walker(context, demo.url)
  context.close()
