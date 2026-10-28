"""The browser harness of the e2e tests: the demo, one page with its waits, and Chromium.

`Demo` serves the demo fixture on a free port with its fake gh under control.
`Walker` holds one page, its console errors, and the waits the tests share.
`scripts/views.py` drives the same harness for the four board views.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "scripts" / "demo.py"
STARTUP_SECONDS = 60
STATUS_CACHE_SECONDS = 15
# the dashboard hides this line once the repo list is in, on success and on failure
REPOS_READY = "#repo-loading"

SETTLE_MS = 100
PUMP_MS = 5
REDUCED = "matchMedia('(prefers-reduced-motion: reduce)').matches"
FRAMES = """(n) => new Promise((done) => {
  const tick = () => (--n > 0 ? requestAnimationFrame(tick) : done());
  requestAnimationFrame(tick);
})"""
MOTION_DONE = """() => {
  // pulses never end, and a scroll-driven fade runs as long as its timeline does
  const ends = (a) => {
    const t = a.effect && a.effect.getTiming();
    return a.timeline === document.timeline && !(t && t.iterations === Infinity);
  };
  if (document.getAnimations().some((a) => a.playState === 'running' && ends(a))) return false;
  const g = window.gsap;
  return !g || !g.globalTimeline.getChildren(true, true, true).some((t) => t.isActive());
}"""
DESKTOP = {"viewport": {"width": 1360, "height": 900}}
PHONE_DEVICE = "iPhone 13"
# the tests provoke these on purpose, so they are narration, not failures
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
    """Toggle the fake gh's slow marker, then read every status again.

    With the marker present every PR has a check that never finishes. The
    fresh read drops the PR checks the server cached under the other state.
    """
    marker = self.gh_state / "slow"
    if on:
      marker.write_text("")
    else:
      marker.unlink(missing_ok=True)
    self.api("/api/fetch", {"force": True})


class Walker:
  """One page with its console errors, and the small reads the tests share."""

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

  def goto(self) -> None:
    """Open the dashboard and wait for its repo list, then for the motion to end."""
    self.page.goto(self.url, wait_until="load")
    self.page.wait_for_selector(REPOS_READY, state="hidden", timeout=15000)
    self.settle()

  def settle(self, floor_ms: int = SETTLE_MS) -> None:
    """Wait until the page motion ends, then a short floor under motion alone.

    GSAP tweens and finite document-timeline animations count. The pulsing
    dots and the scroll-driven fades never end, so they do not hold the wait.
    A page that prefers reduced motion starts no tween, so it skips the floor.
    """
    self.page.wait_for_function(MOTION_DONE, timeout=5000)
    if floor_ms and not self.page.evaluate(REDUCED):
      self.page.wait_for_timeout(floor_ms)

  def frames(self, count: int = 2) -> None:
    """Wait for `count` animation frames: hover, scroll, and input land by then."""
    self.page.evaluate(FRAMES, count)

  def until(self, ready: Callable[[], bool], what: str, timeout_ms: int = 5000) -> None:
    """Pump the browser events until `ready()`, for a held route or a counted request."""
    deadline = time.monotonic() + timeout_ms / 1000
    while not ready():
      if time.monotonic() > deadline:
        raise AssertionError(what)
      self.page.wait_for_timeout(PUMP_MS)

  def visible(self, selector: str) -> bool:
    return self.page.is_visible(selector)

  def text(self, selector: str) -> str:
    return self.page.inner_text(selector)

  def count(self, selector: str) -> int:
    return self.page.eval_on_selector_all(selector, "els => els.length")

  def count_settled(self, selector: str, want: int, timeout_ms: int = 2000) -> int:
    """Read a count once it reaches `want`, or whatever stands at the timeout."""
    from playwright.sync_api import expect

    try:
      expect(self.page.locator(selector)).to_have_count(want, timeout=timeout_ms)
    except AssertionError:
      pass
    return self.count(selector)

  def click(self, selector: str) -> None:
    self.page.click(selector, timeout=8000)
    self.settle()

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


def launch_browser(playwright: Any, chromium: str | None) -> Any:
  options: dict[str, Any] = {}
  if chromium:
    options["executable_path"] = chromium
  return playwright.chromium.launch(**options)
