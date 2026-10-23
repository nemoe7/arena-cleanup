#!/usr/bin/env python3
"""Press every control the UI renders, in a real browser, and check each one did something.

The walk starts its own demo and drives one desktop page, then one phone page.
It saves a screenshot after every step. A step fails on a false assertion, an
exception, or a new console error. The exit code is non-zero when any step
failed.

  uv run scripts/walk.py --out /tmp/walk
  uv run scripts/walk.py --out /tmp/walk --chromium /path/to/chrome

It needs Playwright: `uv sync --group qa`, then `uv run playwright install
chromium`, or `--chromium` with a Chromium binary of your own.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "scripts" / "demo.py"
STARTUP_SECONDS = 60
STATUS_CACHE_SECONDS = 15
DESKTOP = {"viewport": {"width": 1360, "height": 900}}
PHONE_DEVICE = "iPhone 13"
# the walk provokes these on purpose, so they are narration, not failures
INDUCED = ("status of 400", "ERR_INTERNET_DISCONNECTED", "status of 404")

DEMO_REPOS = 5
MIN_TOOLS_READY = 2
MIN_LOG_ROWS = 5
TAP_TARGET_PX = 48
MINUTES_TO_SECONDS = 60
SCROLL_SLACK_PX = 40


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


def launch_browser(playwright: Any, chromium: str | None) -> Any:
  options: dict[str, Any] = {}
  if chromium:
    options["executable_path"] = chromium
  return playwright.chromium.launch(**options)


# -- steps --------------------------------------------------------------------

Step = Callable[[Walker, Demo], None]
STEPS: dict[str, list[tuple[str, Step]]] = {"desktop": [], "phone": []}


class Skip(Exception):
  """Raised by a step that cannot run on this host."""


def step(device: str) -> Callable[[Step], Step]:
  def register(fn: Step) -> Step:
    STEPS[device].append((fn.__name__.replace("_", " "), fn))
    return fn

  return register


def needs_gpg() -> None:
  if shutil.which("gpg") is None:
    raise Skip("the demo has no key without gpg")


@step("desktop")
def no_console_errors_on_load(w: Walker, demo: Demo) -> None:
  w.goto(1500)
  assert w.errors == []


@step("desktop")
def dashboard_renders(w: Walker, demo: Demo) -> None:
  assert w.count(".repo-card") == DEMO_REPOS
  assert "Repos" in w.text(".hero h1")
  assert w.text("#ver").strip() == f"v{demo.api('/api/env')['version']}"
  assert w.count("#env span.on") >= MIN_TOOLS_READY
  assert w.page.get_attribute("#add-source", "placeholder")
  ahead = [int(t) for t in w.page.locator(".arena-row .ahead .n").all_text_contents()]
  assert ahead and max(ahead) > 0, "arena rows show commits beyond the default branch"


@step("desktop")
def typing_into_the_add_box(w: Walker, demo: Demo) -> None:
  w.page.fill("#add-source", "https://github.com/acme/example.git")
  assert w.page.input_value("#add-source").endswith("example.git")


@step("desktop")
def open_repo_from_its_card(w: Walker, demo: Demo) -> None:
  w.goto()
  w.click(".repo-card .repo-name", 800)
  assert w.visible("#view-repo")
  assert "shop-web" in w.text("#repo-title")
  w.click("#back", 600)
  assert w.visible("#view-dashboard")


@step("desktop")
def keyboard_enter_on_a_card(w: Walker, demo: Demo) -> None:
  w.page.focus(".repo-card .repo-name")
  w.page.keyboard.press("Enter")
  w.page.wait_for_timeout(600)
  assert w.visible("#view-repo")
  w.click("#back", 400)


@step("desktop")
def github_access_panel(w: Walker, demo: Demo) -> None:
  w.click("#settings-btn", 1000)
  assert w.visible("#view-settings")
  login = demo.api("/api/auth")["gh"]["login"]
  assert f"@{login}" in w.text("#access-body .banner.ok")
  assert "repo" in w.text("#access-body")  # token scopes


@step("desktop")
def recheck_button_keeps_the_answer(w: Walker, demo: Demo) -> None:
  w.click("text=Re-check", 1200)
  assert w.count("#access-body .banner.ok") >= 1
  w.click("#settings-back")
  assert w.visible("#view-dashboard")


@step("desktop")
def signing_panel(w: Walker, demo: Demo) -> None:
  w.click("#settings-btn", 1000)
  assert w.visible("#view-settings")
  assert w.visible("#gpg-name")
  assert w.visible("#gpg-email")
  assert w.visible("#signing-body .btn.primary")
  assert w.count('a[href="https://github.com/settings/keys"]') == 1


@step("desktop")
def signing_panel_lists_the_demo_key(w: Walker, demo: Demo) -> None:
  needs_gpg()
  assert w.count("#signing-body .sign-row") >= 1
  pills = {
    p.strip()
    for p in w.page.eval_on_selector_all(
      "#signing-body .pill.ok", "els => els.map(e => e.innerText)"
    )
  }
  # the demo stub lists the key under `gh api user/gpg_keys`, so the panel
  # reports it as assigned and shows no warning
  assert {"active", "on GitHub"} <= pills
  assert w.count("#signing-body .banner.ok") >= 1
  assert w.count("#signing-body .banner.warn") == 0


@step("desktop")
def back_from_signing(w: Walker, demo: Demo) -> None:
  w.click("#settings-back")
  assert w.visible("#view-dashboard")


@step("desktop")
def arena_select_lists_the_newest_first(w: Walker, demo: Demo) -> None:
  w.goto(1000)
  assert not w.visible("#opt-arena"), "the select waits for the repo page"
  w.click(".repo-card >> nth=0 >> .repo-name", 800)
  assert not w.visible("#opt-arena"), "one arena branch needs no select"
  w.goto(1000)
  w.click(".repo-card >> nth=4 >> .repo-name", 800)
  assert w.visible("#opt-arena")
  name = w.text("#repo-title").strip()
  repo = next(r for r in demo.api("/api/repos") if r["name"] == name)
  status = repo["status"]
  newest = max(status["activity"], key=status["activity"].get)
  options = [o.get_attribute("value") for o in w.page.locator("#arena option").all()]
  assert len(options) == len(status["arena"]) >= 2
  assert options[0] == newest and w.page.input_value("#arena") == newest
  assert f"--arena {newest}" in w.start_argv()
  w.page.select_option("#arena", options[1])
  w.page.wait_for_timeout(200)
  assert f"--arena {options[1]}" in w.start_argv()
  pressed = '#sidebar button[data-branch][aria-pressed="true"]'
  assert w.page.get_attribute(pressed, "data-branch") == options[1], (
    "the row follows the select"
  )
  w.click(f'#sidebar button[data-branch="{newest}"]', 200)
  assert w.page.input_value("#arena") == newest, "the select follows the row"
  assert w.page.get_attribute(pressed, "data-branch") == newest
  assert f"--arena {newest}" in w.start_argv()
  assert w.page.input_value("#branch") == "", (
    "an arena row never sets the target branch"
  )


@step("desktop")
def sidebar_and_branch_selector(w: Walker, demo: Demo) -> None:
  w.goto(1000)
  w.click(".repo-card .repo-name", 800)
  sidebar = w.text("#sidebar")
  assert "Repo" in sidebar
  assert "arena/session-3" in sidebar
  assert w.count('#sidebar button[data-branch][aria-pressed="true"]') == 1, (
    "one branch, one mark"
  )
  w.click("#sidebar button[data-branch]", 200)
  assert w.page.input_value("#branch") == "", (
    "an arena row never sets the target branch"
  )
  assert "--arena" not in w.start_argv(), "one branch needs no --arena"
  assert w.count("#sidebar .row-btn .ahead") == 1
  assert "HEAD" not in sidebar, "the HEAD block is gone"
  assert w.count("#reset-btn") == 0 and w.count("#divergence") == 0, (
    "origin wins before every run"
  )
  assert w.count("#sidebar .commit") >= 1, "the commits live in the sidebar"
  assert (
    w.page.eval_on_selector("#sidebar", "e => e.getBoundingClientRect().width") == 320
  )
  assert w.page.input_value("#branch") == ""
  options = [o.text_content() for o in w.page.locator("#branch option").all()]
  assert options == ["main (default)"]


@step("desktop")
def option_checkbox_updates_the_argv(w: Walker, demo: Demo) -> None:
  box = 'input[data-opt="dry_run"]'
  w.click(box, 200)
  assert w.page.is_checked(box)
  assert "--dry-run" in w.start_argv()
  w.click(box, 200)
  assert "--dry-run" not in w.start_argv()
  tags = 'input[data-opt="update_tags"]'
  assert w.page.is_checked(tags), "tags move by default"
  w.click(tags, 200)
  assert "--no-tags" in w.start_argv()
  w.click(tags, 200)
  assert "--no-tags" not in w.start_argv()
  assert w.count("#options .desc") == 0 and w.count("#task-note") == 0, "no hint texts"


@step("desktop")
def path_chip_add_and_remove(w: Walker, demo: Demo) -> None:
  w.page.fill("#pathin", "uploads")
  w.page.press("#pathin", "Enter")
  w.page.wait_for_timeout(300)
  assert "--path uploads" in w.start_argv()
  assert w.count(".chip-x") == 1
  w.click(".chip-x button >> nth=0", 300)
  assert "--path" not in w.start_argv()


@step("desktop")
def keyboard_backspace_removes_a_chip(w: Walker, demo: Demo) -> None:
  w.page.fill("#pathin", "docs/old.md")
  w.page.press("#pathin", "Enter")
  w.page.wait_for_timeout(250)
  assert "--path docs/old.md" in w.start_argv()
  w.page.focus("#pathin")
  w.page.keyboard.press("Backspace")
  w.page.wait_for_timeout(250)
  assert "--path docs/old.md" not in w.start_argv()


@step("desktop")
def tree_selector_adds_a_folder_chip(w: Walker, demo: Demo) -> None:
  w.click("#browse", 500)
  assert w.count("#tree .tree-row") > 0
  w.click(".tree-row[aria-expanded] >> nth=0", 500)
  assert w.count(".tree-kids .tree-row") > 0
  w.click(".tree-row[aria-expanded] >> nth=0 >> .tree-select", 300)
  assert w.count(".chip-x") == 1
  assert w.count('.tree-select[aria-pressed="true"]') == 1
  w.click(".chip-x button >> nth=0", 300)
  assert w.count('.tree-select[aria-pressed="true"]') == 0
  w.click("#browse", 300)
  assert w.page.is_hidden("#tree")


@step("desktop")
def timeout_slider_snaps_and_shows_the_number(w: Walker, demo: Demo) -> None:
  assert w.text("#timeout-out") == "15 min"
  assert f"--check-timeout {15 * MINUTES_TO_SECONDS}" in w.start_argv()
  w.page.fill("#timeout", "0")
  w.page.dispatch_event("#timeout", "input")
  w.page.wait_for_timeout(200)
  assert w.text("#timeout-out") == "0 min"
  assert "--check-timeout 0" in w.start_argv()
  w.page.fill("#timeout", "9")
  w.page.dispatch_event("#timeout", "input")
  w.page.wait_for_timeout(200)
  assert w.text("#timeout-out") == "120 min"
  assert f"--check-timeout {120 * MINUTES_TO_SECONDS}" in w.start_argv()
  w.page.fill("#timeout", "3")
  w.page.dispatch_event("#timeout", "input")
  w.page.wait_for_timeout(200)
  assert f"--check-timeout {15 * MINUTES_TO_SECONDS}" in w.start_argv()


@step("desktop")
def start_a_dry_run_and_watch_it_finish(w: Walker, demo: Demo) -> None:
  w.click('input[data-opt="dry_run"]', 0)
  w.click("#start", 0)
  status = w.wait_status("exit")
  assert "exit 0" in status
  # the run card is the story, and the raw log stays open under it
  assert w.page.is_visible("#logwrap")
  assert w.count(".log-row") > MIN_LOG_ROWS


@step("desktop")
def cancel_a_run_in_flight(w: Walker, demo: Demo) -> None:
  w.click("#back")
  w.click(".repo-card >> nth=2 >> .repo-name", 900)
  assert "docs-site" in w.text("#repo-title")
  # The demo fixtures finish in a fraction of a second. The stub gh reports a check that
  # never finishes, so the run parks at the PR gate. Only there Cancel meets a live process.
  demo.slow_checks(True)
  try:
    box = 'input[data-opt="dry_run"]'
    if w.page.is_checked(box):
      w.click(box, 150)
    w.click("#start", 0)
    w.page.wait_for_function(
      "() => document.querySelector('#log').innerText.includes('still running, waiting up to')",
      timeout=30000,
    )
    assert w.text("#start") == "Cancel", "the one button turned into Cancel"
    w.click("#start", 0)
    status = w.wait_status("cancelled", timeout=20000)
  finally:
    demo.slow_checks(False)
  assert "cancelled" in status.lower()
  assert not w.page.eval_on_selector("#start", "e => e.disabled"), (
    "Start stayed disabled"
  )


@step("desktop")
def copy_the_log(w: Walker, demo: Demo) -> None:
  w.click("#back")
  w.click(".repo-card >> nth=0 >> .repo-name", 800)
  w.click('input[data-opt="dry_run"]', 0)
  w.click("#start", 0)
  w.wait_status("exit")
  w.click("#copy", 400)
  assert "copied" in w.text("#toast")


@step("desktop")
def jump_to_latest_button(w: Walker, demo: Demo) -> None:
  # the button only exists for an overflowing log, so constrain the panel to
  # reproduce the condition a long run creates
  w.page.eval_on_selector(
    "#log",
    "e => { e.style.flex = 'none'; e.style.height = '120px'; e.style.maxHeight = '120px'; e.style.overflow = 'auto'; }",
  )
  w.page.eval_on_selector(
    "#log", "e => { e.scrollTop = 0; e.dispatchEvent(new Event('scroll')); }"
  )
  w.page.wait_for_timeout(300)
  w.click("#jump", 400)
  assert w.page.eval_on_selector(
    "#log", f"e => e.scrollHeight - e.scrollTop - e.clientHeight < {SCROLL_SLACK_PX}"
  )


@step("desktop")
def keyboard_ctrl_enter_starts(w: Walker, demo: Demo) -> None:
  w.page.keyboard.press("Control+Enter")
  w.page.wait_for_timeout(400)
  running = w.status_text()
  assert running in ("starting", "running") or "exit" in running
  w.wait_status("exit")


@step("desktop")
def adding_a_bad_path_reports_an_error(w: Walker, demo: Demo) -> None:
  w.goto(1000)
  w.page.fill("#add-source", "/definitely/not/a/repo")
  w.click("#add-btn", 1200)
  assert w.text("#toast").strip()


@step("desktop")
def empty_add_is_a_no_op(w: Walker, demo: Demo) -> None:
  before = w.count(".repo-card")
  w.page.fill("#add-source", "   ")
  w.click("#add-btn", 600)
  assert w.count(".repo-card") == before


@step("desktop")
def signed_out_banner_and_honest_pills(w: Walker, demo: Demo) -> None:
  demo.sign_in(False)
  demo.wait_until_checked(False)
  w.goto(2500)
  assert w.visible("#auth-banner")
  pills = w.page.eval_on_selector_all(
    ".arena-row .pill:not(.ahead)", "els => els.map(e => e.innerText)"
  )
  assert pills
  assert all("checks unavailable" in p for p in pills), pills


@step("desktop")
def connect_github_opens_access_with_a_token_field(w: Walker, demo: Demo) -> None:
  w.click("#auth-banner button", 1000)
  assert w.visible("#view-settings")
  assert w.visible("#token-input")


@step("desktop")
def a_junk_token_is_rejected(w: Walker, demo: Demo) -> None:
  w.page.fill("#token-input", "not a token")
  w.click("#token-btn", 1200)
  assert "token" in w.text("#toast").lower()


@step("desktop")
def sign_in_with_a_token(w: Walker, demo: Demo) -> None:
  w.page.fill("#token-input", "ghp_walkthrough123")
  w.click("#token-btn", 2000)
  assert w.count("#access-body .banner.ok") >= 1


@step("desktop")
def checks_come_back_after_signing_in(w: Walker, demo: Demo) -> None:
  w.click("#settings-back", 400)
  demo.wait_until_checked(True)
  w.goto(2200)
  pills = w.page.eval_on_selector_all(
    ".arena-row .pill:not(.ahead)", "els => els.map(e => e.innerText)"
  )
  assert any("PR #" in p for p in pills), pills
  demo.sign_in(True)


@step("desktop")
def offline_shell_loads_and_server_is_called_out(w: Walker, demo: Demo) -> None:
  w.goto(2000)
  w.context.set_offline(True)
  w.page.reload(wait_until="domcontentloaded")
  w.page.wait_for_timeout(1800)
  assert w.visible("#offline-banner")
  assert w.text("#offline-banner").strip()
  assert w.page.is_hidden("#repo-grid"), "grid rendered from nothing"


@step("desktop")
def back_online_recovers_automatically(w: Walker, demo: Demo) -> None:
  w.context.set_offline(False)
  w.page.evaluate("window.dispatchEvent(new Event('online'))")
  w.page.wait_for_timeout(2000)
  assert not w.visible("#offline-banner")
  assert w.count(".repo-card") == DEMO_REPOS


@step("phone")
def phone_loads(w: Walker, demo: Demo) -> None:
  w.goto(1500)
  assert w.count(".repo-card") == DEMO_REPOS


@step("phone")
def phone_tab_bar_in_the_repo_view(w: Walker, demo: Demo) -> None:
  w.click(".repo-card .repo-name", 700)
  assert w.visible("#tabbar")


@step("phone")
def phone_stacks_the_sidebar_below_the_run(w: Walker, demo: Demo) -> None:
  top = "e => e.getBoundingClientRect().top"
  assert w.visible("#sidebar")
  assert w.page.eval_on_selector("#sidebar", top) > w.page.eval_on_selector(
    "#console-card", top
  )
  assert w.count("#sidebar .commit") >= 1
  box = "e => [e.clientHeight, e.scrollHeight]"
  shown, full = w.page.eval_on_selector("#commits", box)
  assert shown == full, "the list grows with the page, no inner scroll"


@step("phone")
def phone_paste_box_is_a_tap_target(w: Walker, demo: Demo) -> None:
  w.click("#back")
  height = w.page.eval_on_selector(
    "#add-source", "e => Math.round(e.getBoundingClientRect().height)"
  )
  assert height >= TAP_TARGET_PX


@step("phone")
def phone_clean_and_push_runs(w: Walker, demo: Demo) -> None:
  w.click(".repo-card .repo-name", 700)
  w.click("#start-mobile", 4000)
  assert w.status_text().strip()


# -- runner -------------------------------------------------------------------


def run_steps(
  device: str, walker: Walker, demo: Demo, out: Path
) -> list[dict[str, Any]]:
  results = []
  seen_errors = 0
  for index, (name, fn) in enumerate(STEPS[device]):
    record: dict[str, Any] = {"device": device, "step": name, "ok": True}
    started = time.monotonic()
    try:
      fn(walker, demo)
      if len(walker.errors) > seen_errors:
        raise AssertionError("console: " + "; ".join(walker.errors[seen_errors:]))
    except Skip as skip:
      record.update(ok=None, skipped=str(skip))
    except Exception as exc:
      record.update(ok=False, error=f"{type(exc).__name__}: {exc}".strip())
      record["trace"] = traceback.format_exc(limit=-3)
    seen_errors = len(walker.errors)
    record["ms"] = round((time.monotonic() - started) * 1000)
    shot = out / f"{device}-{index:02d}-{name.replace(' ', '-')}.png"
    try:
      walker.page.screenshot(path=str(shot), full_page=True)
      record["screenshot"] = shot.name
    except Exception as exc:
      record["screenshot_error"] = str(exc).splitlines()[0]
    mark = {True: "ok  ", False: "FAIL", None: "skip"}[record["ok"]]
    detail = record.get("error") or record.get("skipped") or ""
    print(f"{mark} {device} {index:02d} {name} {detail}".rstrip(), flush=True)
    results.append(record)
  return results


def walk(out: Path, chromium: str | None) -> int:
  from playwright.sync_api import sync_playwright

  out.mkdir(parents=True, exist_ok=True)
  results: list[dict[str, Any]] = []
  with tempfile.TemporaryDirectory(prefix="walk-demo-") as tmp:
    demo = Demo(Path(tmp) / "demo")
    try:
      with sync_playwright() as playwright:
        browser = launch_browser(playwright, chromium)
        for device, options in (
          ("desktop", DESKTOP),
          ("phone", playwright.devices[PHONE_DEVICE]),
        ):
          context = browser.new_context(**options)
          try:
            results += run_steps(device, Walker(context, demo.url), demo, out)
          finally:
            context.close()
        browser.close()
    finally:
      demo.stop()
  failed = [r for r in results if r["ok"] is False]
  skipped = [r for r in results if r["ok"] is None]
  summary = {
    "steps": len(results),
    "failed": len(failed),
    "skipped": len(skipped),
    "results": results,
  }
  (out / "walk-report.json").write_text(json.dumps(summary, indent=2) + "\n")
  print(
    f"walk: {len(results)} steps, {len(failed)} failed, {len(skipped)} skipped -> {out}"
  )
  return 1 if failed else 0


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument(
    "--out", required=True, type=Path, help="screenshot and report directory"
  )
  parser.add_argument(
    "--chromium",
    default=os.environ.get("WALK_CHROMIUM"),
    help="a Chromium binary to use instead of the one `playwright install` fetched",
  )
  args = parser.parse_args()
  return walk(args.out, args.chromium)


if __name__ == "__main__":
  sys.exit(main())
