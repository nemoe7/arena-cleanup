"""A demo instance plus a real Chromium for the browser walk.

Set `E2E_CHROMIUM` to a Chromium binary to run without `playwright install`.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from ..conftest import ROOT

DEMO = ROOT / "scripts" / "demo.py"
STARTUP_SECONDS = 60
STATUS_CACHE_SECONDS = 15
DESKTOP = {"viewport": {"width": 1360, "height": 900}}
# the walk provokes these on purpose, so they are narration, not failures
INDUCED = ("status of 400", "ERR_INTERNET_DISCONNECTED", "status of 404")


def free_port() -> int:
  with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    return sock.getsockname()[1]


class Demo:
  """The demo fixture served on a free port, with its fake gh under control."""

  def __init__(self, root: Path) -> None:
    self.root = root
    self.port = free_port()
    self.url = f"http://127.0.0.1:{self.port}"
    self.proc = subprocess.Popen(
      [
        sys.executable,
        str(DEMO),
        "--root",
        str(root),
        "--host",
        "127.0.0.1",
        "--port",
        str(self.port),
      ],
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + STARTUP_SECONDS
    while time.monotonic() < deadline:
      if self.proc.poll() is not None:
        raise RuntimeError(
          f"demo exited: {self.proc.stdout.read().decode(errors='replace')[-2000:]}"
        )
      try:
        urllib.request.urlopen(f"{self.url}/api/env", timeout=2).read()
        return
      except (urllib.error.URLError, ConnectionError, TimeoutError):
        time.sleep(0.25)
    raise RuntimeError("the demo did not start")

  def stop(self) -> None:
    self.proc.terminate()
    try:
      self.proc.wait(timeout=STARTUP_SECONDS)
    except subprocess.TimeoutExpired:
      self.proc.kill()

  @property
  def gh_state(self) -> Path:
    return self.root / "gh"

  def api(self, path: str, body: dict[str, Any] | None = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(
      self.url + path, data=data, headers=headers, method="POST" if body else "GET"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
      return json.loads(resp.read())

  def wait_until_checked(self, checked: bool) -> list[dict[str, Any]]:
    """Wait for the server's status cache to agree with the fake gh's sign-in state."""
    deadline = time.monotonic() + STATUS_CACHE_SECONDS
    repos = self.api("/api/repos")
    while time.monotonic() < deadline and any(
      r["status"]["pr_checked"] is not checked for r in repos
    ):
      time.sleep(0.5)
      repos = self.api("/api/repos")
    return repos

  def sign_in(self, on: bool) -> None:
    """Toggle the fake gh's signed-in marker, then drop the server's auth cache."""
    marker = self.gh_state / "signed-in"
    if on:
      marker.write_text("")
    else:
      marker.unlink(missing_ok=True)
    self.api("/api/auth", {"action": "check"})

  def slow_checks(self, on: bool) -> None:
    """With the marker present every PR has a check that never finishes."""
    marker = self.gh_state / "slow"
    if on:
      marker.write_text("")
    else:
      marker.unlink(missing_ok=True)


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
  options: dict[str, Any] = {}
  if os.environ.get("E2E_CHROMIUM"):
    options["executable_path"] = os.environ["E2E_CHROMIUM"]
  try:
    instance = playwright.chromium.launch(**options)
  except Exception as exc:
    pytest.skip(f"no Chromium for Playwright: {str(exc).splitlines()[0]}")
  yield instance
  instance.close()


class Walker:
  """One page with its console errors, and the small assertions the walk uses."""

  def __init__(self, context: Any, url: str) -> None:
    self.context = context
    self.page = context.new_page()
    self.page.set_default_timeout(10000)
    self.url = url
    self.errors: list[str] = []
    self.page.on("pageerror", lambda exc: self.errors.append(str(exc)))
    self.page.on("console", self._on_console)

  def _on_console(self, message: Any) -> None:
    if message.type == "error" and not any(
      marker in message.text for marker in INDUCED
    ):
      self.errors.append(message.text)

  def goto(self, settle_ms: int = 1200) -> None:
    self.page.goto(self.url, wait_until="networkidle")
    self.page.wait_for_timeout(settle_ms)

  def visible(self, selector: str) -> bool:
    return self.page.is_visible(selector)

  def text(self, selector: str) -> str:
    return self.page.inner_text(selector)

  def count(self, selector: str) -> int:
    return self.page.eval_on_selector_all(selector, "els => els.length")

  def click(self, selector: str, settle_ms: int = 500) -> None:
    self.page.click(selector, timeout=8000)
    self.page.wait_for_timeout(settle_ms)

  def start_argv(self) -> str:
    """The argv the Start button will run, exposed as a data attribute."""
    return self.page.eval_on_selector("#start", "e => e.dataset.argv || ''")

  def status_text(self) -> str:
    return self.page.inner_text("#statustext")

  def wait_status(self, token: str, timeout: int = 30000) -> str:
    self.page.wait_for_function(
      f"() => document.querySelector('#statustext').textContent.includes({json.dumps(token)})",
      timeout=timeout,
    )
    return self.status_text()

  def log_hidden(self) -> bool:
    return self.page.eval_on_selector("#logwrap", "e => e.hidden")

  def open_log(self) -> None:
    if self.log_hidden():
      self.click("#logtoggle", 250)


@pytest.fixture(scope="module")
def desktop(browser: Any, demo: Demo) -> Iterator[Walker]:
  context = browser.new_context(**DESKTOP)
  yield Walker(context, demo.url)
  context.close()


@pytest.fixture(scope="module")
def phone(browser: Any, playwright: Any, demo: Demo) -> Iterator[Walker]:
  context = browser.new_context(**playwright.devices["iPhone 13"])
  yield Walker(context, demo.url)
  context.close()
