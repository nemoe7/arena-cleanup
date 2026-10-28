"""A demo instance plus a real Chromium for the browser tests.

The page objects live in `scripts/walk.py`, the hand-run walk. Set
`E2E_CHROMIUM` to a Chromium binary to run without `playwright install`.

The contexts ask for reduced motion, which the page honours. No tween runs,
so each settled wait ends at its floor. A module marked `motion` keeps the
tweens, since it tests them.
"""

from __future__ import annotations

import os
import shutil
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


@pytest.fixture
def signing() -> None:
  """A parked run signs before its PR gate, so it needs gpg."""
  if shutil.which("gpg") is None:
    pytest.skip("no gpg: the run cannot reach its checks wait")


def motion(request: pytest.FixtureRequest) -> dict[str, str]:
  """Context options for the module's motion: reduced unless it is marked `motion`."""
  if request.node.get_closest_marker("motion"):
    return {}
  return {"reduced_motion": "reduce"}


@pytest.fixture(scope="module")
def desktop(
  request: pytest.FixtureRequest, browser: Any, demo: Demo
) -> Iterator[Walker]:
  context = browser.new_context(**DESKTOP, **motion(request))
  yield Walker(context, demo.url)
  context.close()


@pytest.fixture(scope="module")
def phone(
  request: pytest.FixtureRequest, browser: Any, playwright: Any, demo: Demo
) -> Iterator[Walker]:
  context = browser.new_context(**playwright.devices[PHONE_DEVICE], **motion(request))
  yield Walker(context, demo.url)
  context.close()
