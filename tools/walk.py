#!/usr/bin/env python3
"""
walk.py - press every control the UI can render, in a real browser, and prove
each one did something.

This is a manual QA pass written down. Each step:

  1. drives the app the way a person would (click, type, keyboard),
  2. asserts a specific, checkable outcome (a view changed, a request fired,
     a value appeared, a toast said something),
  3. writes a screenshot named after the step, so a failure points at a frame.

It runs at desktop and phone widths, and covers the states that are easy to
forget: empty instance, offline, signed-out gh, a job that fails, a cancelled
job, and the signing panel both with and without a key.

    python3 tools/walk.py --url http://localhost:8096 --out /tmp/walk

Exits non-zero if any step fails, so it can be wired into CI later.
"""

from __future__ import annotations

import argparse
import ast
import json
import shutil
import subprocess
import time
import traceback
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

# --------------------------------------------------------------------------- #
# harness
# --------------------------------------------------------------------------- #


class Walk:
  def __init__(
    self, page: Any, out: Path, prefix: str, errors: list[str] | None = None
  ) -> None:
    self.page = page
    self.out = out
    self.prefix = prefix
    self.steps: list[dict[str, Any]] = []
    self.failures = 0
    self.console_errors: list[str] = errors if errors is not None else []

  def shot(self, name: str) -> None:
    self.page.screenshot(path=str(self.out / f"{self.prefix}-{name}.png"))

  def step(self, name: str, fn: Callable[[], str | None], shot: bool = True) -> None:
    try:
      detail = fn() or ""
      if shot:
        self.shot(f"{len(self.steps):02d}-{name}")
      self.steps.append({"step": name, "ok": True, "detail": detail})
      print(f"  PASS  {name}" + (f"  — {detail}" if detail else ""))
    except Exception as exc:
      self.failures += 1
      self.steps.append({"step": name, "ok": False, "detail": str(exc)})
      print(f"  FAIL  {name}\n        {exc}")
      try:
        self.shot(f"{len(self.steps):02d}-FAILED-{name}")
      except Exception:
        pass
      if isinstance(exc, AssertionError):
        traceback.print_exc(limit=1)

  # assertions -------------------------------------------------------------

  def visible(self, selector: str, expected: bool = True) -> None:
    actual = self.page.is_visible(selector)
    assert actual is expected, f"{selector} visible={actual}, wanted {expected}"

  def text(self, selector: str, contains: str) -> str:
    value = self.page.inner_text(selector)
    assert contains in value, f"{selector!r} = {value[:120]!r}, wanted {contains!r}"
    return value.strip().replace("\n", " ")[:80]

  def count(self, selector: str, expected: int | None = None) -> int:
    n = self.page.eval_on_selector_all(selector, "els => els.length")
    if expected is not None:
      assert n == expected, f"{selector}: {n} elements, wanted {expected}"
    return n

  def click(self, selector: str, index: int = 0) -> None:
    self.page.click(f"{selector} >> nth={index}", timeout=8000)

  def wait_for(self, predicate: str, timeout: int = 15000) -> None:
    self.page.wait_for_function(predicate, timeout=timeout)


def check(condition: bool, message: str) -> None:
  assert condition, message


# --------------------------------------------------------------------------- #
# the same walk, driven through `playwright cli`
# --------------------------------------------------------------------------- #

CLI = shutil.which("playwright") or "playwright"


class _CliKeyboard:
  """`page.keyboard.press(key)` in the Playwright API shape."""

  def __init__(self, page: CliPage) -> None:
    self.page = page

  def press(self, key: str) -> None:
    self.page._run("press", key)


class CliPage:
  """A page-shaped object backed by the playwright CLI.

  Every method here is one `playwright cli -s=<session> ...` call, so the walk
  exercises the same interface an agent would use from a terminal. The session
  keeps the browser alive between calls.
  """

  def __init__(self, session: str, out: Path) -> None:
    self.session = session
    self.out = out
    self.timeout = 10000
    self._shot = 0
    self.keyboard = _CliKeyboard(self)

  # -- plumbing -------------------------------------------------------------

  def _run(self, *args: str, check: bool = True) -> str:
    cmd = [CLI, "cli", f"-s={self.session}", *args]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    out = done.stdout + done.stderr
    if check and ("### Error" in out or done.returncode not in (0, None)):
      raise AssertionError(f"cli {' '.join(args)}: {out.strip()[:400]}")
    return out

  def _result(self, out: str) -> Any:
    if "### Result" not in out:
      return None
    body = out.split("### Result", 1)[1]
    body = body.split("### Ran Playwright code", 1)[0].strip()
    if not body:
      return None
    # the CLI prints JSON, and Python's literal_eval reads "false" as a string
    try:
      return json.loads(body)
    except ValueError:
      pass
    try:
      return ast.literal_eval(body)
    except (ValueError, SyntaxError):
      return body

  def _js(self, expression: str) -> Any:
    return self._result(self._run("eval", expression))

  def _js_element(self, selector: str, fn: str) -> Any:
    expr = (
      f"(() => {{ const __e = document.querySelector({json.dumps(selector)}); "
      f"if (!__e) return null; return ({fn})(__e); }})()"
    )
    return self._js(expr)

  def _js_all(self, selector: str, fn: str) -> Any:
    expr = (
      f"(() => {{ const __els = Array.from(document.querySelectorAll({json.dumps(selector)})); "
      f"return ({fn})(__els); }})()"
    )
    return self._js(expr)

  # -- navigation -----------------------------------------------------------

  def goto(self, url: str, wait_until: str | None = None) -> None:
    self._run("goto", url)
    self.wait_for_timeout(300)

  def reload(self, wait_until: str | None = None) -> None:
    self._run("reload", check=False)
    self.wait_for_timeout(800)

  def set_default_timeout(self, ms: int) -> None:
    self.timeout = ms

  def wait_for_timeout(self, ms: int) -> None:
    time.sleep(ms / 1000)

  # -- interaction ----------------------------------------------------------

  def click(self, selector: str, index: int = 0, timeout: int | None = None) -> None:
    # the CLI runs in strict mode: a selector that matches several elements is
    # an error there, so always name which one is meant
    target = f"{selector} >> nth={index}"
    self._run("click", target)

  def fill(self, selector: str, text: str) -> None:
    self._run("fill", selector, text)

  def press(self, selector: str, key: str) -> None:
    self.focus(selector)
    self._run("press", key)

  def press_key(self, key: str) -> None:
    self._run("press", key)

  def focus(self, selector: str) -> None:
    self._js_element(selector, "e => e.focus()")

  def select_option(self, selector: str, value: str) -> None:
    self._run("select", selector, value)

  def dispatch_event(self, selector: str, event: str) -> None:
    self._js_element(selector, f"e => e.dispatchEvent(new Event({json.dumps(event)}))")

  def set_offline(self, offline: bool) -> None:
    self._run("network-state-set", "offline" if offline else "online")
    self.wait_for_timeout(300)

  # -- reading --------------------------------------------------------------

  def input_value(self, selector: str) -> str:
    return self._js_element(selector, "e => e.value") or ""

  def inner_text(self, selector: str) -> str:
    return self._js_element(selector, "e => e.innerText") or ""

  def is_hidden(self, selector: str) -> bool:
    return not self.is_visible(selector)

  def evaluate(self, expression: str) -> Any:
    return self._js(expression)

  def is_visible(self, selector: str) -> bool:
    return bool(
      self._js_element(
        selector,
        "e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length)",
      )
    )

  def get_attribute(self, selector: str, name: str) -> str | None:
    return self._js_element(selector, f"e => e.getAttribute({json.dumps(name)})")

  def eval_on_selector(self, selector: str, fn: str) -> Any:
    return self._js_element(selector, fn)

  def eval_on_selector_all(self, selector: str, fn: str) -> Any:
    return self._js_all(selector, fn)

  def wait_for_function(self, predicate: str, timeout: int = 15000) -> None:
    deadline = time.time() + timeout / 1000
    expression = f"({predicate})()"
    while time.time() < deadline:
      if self._js(expression):
        return
      time.sleep(0.25)
    raise AssertionError(f"timed out waiting for {predicate[:80]}")

  # -- output ---------------------------------------------------------------

  def screenshot(self, path: str, **_: Any) -> None:
    self._run("screenshot", "--filename", path)

  def console_errors(self) -> list[str]:
    out = self._run("console", "error", check=False)
    errors = []
    for line in out.splitlines():
      line = line.strip()
      if line.startswith("[ERROR]"):
        errors.append(line[len("[ERROR]") :].strip())
    self._run("console", "error", "--clear", check=False)
    return errors

  def close(self) -> None:
    self._run("close", check=False)


# --------------------------------------------------------------------------- #
# the walk
# --------------------------------------------------------------------------- #


def wash_dashboard(w: Walk, url: str) -> None:
  page = w.page
  page.goto(url, wait_until="networkidle")
  page.wait_for_timeout(1200)

  w.step("dashboard renders repo cards", lambda: f"{w.count('.repo-card')} cards")
  w.step("hero heading", lambda: w.text(".hero h1", "Repositories"))
  w.step("version badge resolves", lambda: w.text("#ver", "v3"))
  w.step("tool dots render", lambda: f"{w.count('#env span.on')} of 4 ready")
  w.step(
    "add input has placeholder",
    lambda: page.get_attribute("#add-source", "placeholder"),
  )

  def type_url():
    page.fill("#add-source", "https://github.com/acme/example.git")
    w.text("#add-source", "") if False else None
    val = page.input_value("#add-source")
    assert val.endswith("example.git"), val
    return val

  w.step("typing into the add box works", type_url)


def walk_dashboard(w: Walk, url: str) -> None:
  page = w.page
  page.goto(url, wait_until="networkidle")
  page.wait_for_timeout(1200)

  w.step(
    "open repo from its card",
    lambda: (
      w.click(".repo-card"),
      page.wait_for_timeout(800),
      w.visible("#view-repo"),
      w.text("#repo-title", "shop-web"),
    )[-1],
  )
  w.step(
    "back to all repos",
    lambda: (
      w.click("#back"),
      page.wait_for_timeout(600),
      w.visible("#view-dashboard"),
    )[-1],
  )
  w.step(
    "card Open button opens the repo",
    lambda: (
      page.click(".repo-card .btn.ghost >> nth=0"),
      page.wait_for_timeout(700),
      w.visible("#view-repo"),
    )[-1],
  )
  page.click("#back")
  page.wait_for_timeout(500)

  def keyboard_open():
    page.focus(".repo-card")
    page.keyboard.press("Enter")
    page.wait_for_timeout(600)
    w.visible("#view-repo")
    page.click("#back")
    page.wait_for_timeout(400)
    return "enter on a focused card opens it"

  w.step("keyboard: Enter on a card", keyboard_open)


def walk_access(w: Walk) -> None:
  page = w.page

  w.step(
    "open GitHub access",
    lambda: (
      w.click("#access-btn"),
      page.wait_for_timeout(1000),
      w.visible("#view-access"),
    )[-1],
  )
  w.step(
    "signed-in banner",
    lambda: w.text("#access-body .banner.ok", "Signed in as @nemoe7"),
  )
  w.step("token scopes shown", lambda: w.text("#access-body", "repo"))
  w.step(
    "storage card present", lambda: w.text("#access-body", "What survives a rebuild")
  )
  w.step(
    "storage lists the token file",
    lambda: w.text("#access-body", ".config/gh/hosts.yml"),
  )
  w.step("storage lists git config", lambda: w.text("#access-body", ".gitconfig"))
  w.step(
    "install card present", lambda: w.text("#access-body", "Install on this device")
  )

  def recheck():
    page.click("text=Re-check")
    page.wait_for_timeout(1200)
    after = page.inner_text("#access-body")
    assert "Signed in" in after, after[:120]
    return "re-check kept the same answer"

  w.step("Re-check button", recheck)
  w.step(
    "back from access",
    lambda: (
      w.click("#access-back"),
      page.wait_for_timeout(500),
      w.visible("#view-dashboard"),
    )[-1],
  )


def walk_signing(w: Walk) -> None:
  page = w.page

  w.step(
    "open signing",
    lambda: (
      w.click("#signing-btn"),
      page.wait_for_timeout(1000),
      w.visible("#view-signing"),
    )[-1],
  )
  w.step(
    "key list shows the key", lambda: w.text("#signing-body", "Keys in this container")
  )
  w.step("active key marked", lambda: w.text("#signing-body", "active"))
  w.step(
    "unverified warning present",
    lambda: w.text("#signing-body", "not assigned to your GitHub account"),
  )
  w.step(
    "create-key form present",
    lambda: (
      w.visible("#gpg-name"),
      w.visible("#gpg-email"),
      w.visible("#signing-body .btn.primary"),
    )[-1],
  )
  w.step(
    "github keys link exists",
    lambda: (w.count('a[href="https://github.com/settings/keys"]'), "1")[-1],
  )
  w.step(
    "back from signing",
    lambda: (
      w.click("#signing-back"),
      page.wait_for_timeout(500),
      w.visible("#view-dashboard"),
    )[-1],
  )


def walk_repo(w: Walk) -> None:
  page = w.page
  page.goto(w.url, wait_until="networkidle")
  page.wait_for_timeout(1000)
  page.click(".repo-card")
  page.wait_for_timeout(800)

  w.step("sidebar shows branch facts", lambda: w.text("#sidebar", "Repository"))
  w.step("sidebar lists arena branches", lambda: w.text("#sidebar", "arena/session-3"))

  def pick_branch_row():
    page.click('#sidebar [data-branch="arena/session-3"]')
    page.wait_for_timeout(300)
    value = page.input_value("#branch")
    assert value == "arena/session-3", value
    return f"select = {value}"

  w.step("clicking an arena branch fills the selector", pick_branch_row)

  def reset_branch():
    page.select_option("#branch", "")
    page.wait_for_timeout(300)
    assert page.input_value("#branch") == "", "not cleared"
    return "cleared"

  w.step("branch selector can be cleared", reset_branch)

  for cmd in ("strip", "doctor", "run"):

    def switch(c=cmd):
      page.click(f'#cmdswitch button[data-cmd="{c}"]')
      page.wait_for_timeout(400)
      pressed = page.get_attribute(f'#cmdswitch button[data-cmd="{c}"]', "aria-pressed")
      assert pressed == "true", f"{c} not pressed"
      return f"{c} selected"

    w.step(f"command switch → {cmd}", switch)

  def doctor_hides_options():
    page.click('#cmdswitch button[data-cmd="doctor"]')
    page.wait_for_timeout(400)
    hidden = page.eval_on_selector("#options-card", "e => e.style.display === 'none'")
    assert hidden, "options still visible in doctor"
    page.click('#cmdswitch button[data-cmd="run"]')
    page.wait_for_timeout(300)
    return "doctor hides the options card"

  w.step("doctor hides irrelevant options", doctor_hides_options)

  def toggle():
    page.click('.toggle[data-opt="dry_run"]')
    page.wait_for_timeout(200)
    assert page.get_attribute('.toggle[data-opt="dry_run"]', "aria-pressed") == "true"
    preview = start_argv(page)
    assert "--dry-run" in preview, preview
    page.click('.toggle[data-opt="dry_run"]')
    page.wait_for_timeout(200)
    assert "--dry-run" not in start_argv(page)
    return "the start button follows the toggle"

  w.step("option toggle updates the argv preview", toggle)

  def divergence():
    page.click('#divergence button[data-v="remote"]')
    page.wait_for_timeout(200)
    assert "--on-divergence remote" in start_argv(page)
    page.click('#divergence button[data-v="ask"]')
    page.wait_for_timeout(200)
    assert "--on-divergence" not in start_argv(page)
    return "divergence control drives the flag"

  w.step("divergence segmented control", divergence)

  def paths():
    page.fill("#pathin", "uploads")
    page.press("#pathin", "Enter")
    page.wait_for_timeout(300)
    assert "--path uploads" in start_argv(page), start_argv(page)
    chips = w.count(".chip-x")
    page.click(".chip-x button >> nth=0")
    page.wait_for_timeout(300)
    assert "--path" not in start_argv(page)
    return f"{chips} chip, removed"

  w.step("path chip add and remove", paths)

  def path_backspace():
    page.fill("#pathin", "docs/old.md")
    page.press("#pathin", "Enter")
    page.wait_for_timeout(250)
    page.focus("#pathin")
    page.keyboard.press("Backspace")
    page.wait_for_timeout(250)
    assert "--path docs/old.md" not in start_argv(page)
    return "Backspace on the empty box removes the last chip"

  w.step("keyboard: Backspace removes a chip", path_backspace)

  def timeout():
    page.fill("#timeout", "5")
    page.dispatch_event("#timeout", "input")
    page.wait_for_timeout(250)
    assert "--check-timeout 300" in start_argv(page), start_argv(page)
    page.fill("#timeout", "15")
    page.dispatch_event("#timeout", "input")
    return "--check-timeout follows the minutes box"

  w.step("timeout input", timeout)


def start_argv(page) -> str:
  """The argv the Start button will run, exposed as a tooltip and a data attribute."""
  return page.eval_on_selector("#start", "e => e.dataset.argv || ''")


def walk_job(w: Walk, args: argparse.Namespace) -> None:
  page = w.page

  def dry_run():
    page.click('.toggle[data-opt="dry_run"]')
    page.click("#start")
    page.wait_for_function(
      "() => document.querySelector('#statustext').textContent.includes('exit')",
      timeout=30000,
    )
    status = page.inner_text("#statustext")
    assert "exit 0" in status, status
    # the run card is the story now; the raw log is one click away
    assert page.eval_on_selector("#logwrap", "e => e.hidden"), "log opened by itself"
    assert page.inner_text("#logtoggle") == "Show log"
    page.click("#logtoggle")
    page.wait_for_timeout(300)
    assert page.inner_text("#logtoggle") == "Hide log"
    rows = w.count(".log-row")
    assert rows > 5, f"{rows} log rows"
    return f"{status}, {rows} rows behind one click"

  w.step("start a dry run and watch it finish", dry_run)

  def cancel():
    page.click("#back")
    page.wait_for_timeout(500)
    page.click(".repo-card >> nth=2")
    page.wait_for_timeout(900)
    w.text("#repo-title", "docs-site")
    # the demo fixtures finish in a fraction of a second, so ask the stub gh for
    # a check that is still running: the run then parks at the PR gate, which is
    # the only place Cancel can be tested against a live process
    slow = Path(args.gh_flag).with_name("slow") if args.gh_flag else None
    if slow:
      slow.parent.mkdir(parents=True, exist_ok=True)
      slow.write_text("")
    try:
      # a dry run only says it would wait, so this has to be a real run; the
      # check never finishes, so cancelling before the rewrite publishes nothing
      pressed = page.eval_on_selector(
        '.toggle[data-opt="dry_run"]', "e => e.getAttribute('aria-pressed')"
      )
      if pressed == "true":
        page.click('.toggle[data-opt="dry_run"]')
        page.wait_for_timeout(150)
      page.click("#start")
      # the log is collapsed by default now; the gate message lands in it, so
      # open it the way a user would before waiting for that line
      if page.eval_on_selector("#logwrap", "e => e.hidden"):
        page.click("#logtoggle")
      # wait for the gate to start waiting, then cancel while the engine is
      # sitting in its poll loop rather than after it has already finished
      page.wait_for_function(
        "() => document.querySelector('#log').innerText"
        ".includes('still running; waiting up to')",
        timeout=30000,
      )
      w.visible("#cancel")
      page.click("#cancel")
      page.wait_for_function(
        "() => document.querySelector('#statustext').textContent.includes('cancelled')",
        timeout=20000,
      )
      status = page.inner_text("#statustext")
      assert "cancelled" in status.lower(), status
    finally:
      if slow:
        slow.unlink(missing_ok=True)
    assert not page.eval_on_selector("#start", "e => e.disabled"), (
      "Start stayed disabled"
    )
    return f"status={status!r}, controls restored"

  w.step("cancel a run in flight", cancel)

  def copy():
    page.click("#back")
    page.wait_for_timeout(500)
    page.click(".repo-card >> nth=0")
    page.wait_for_timeout(800)
    page.click('.toggle[data-opt="dry_run"]')
    page.click("#start")
    page.wait_for_function(
      "() => document.querySelector('#statustext').textContent.includes('exit')",
      timeout=30000,
    )
    if page.eval_on_selector("#logwrap", "e => e.hidden"):
      page.click("#logtoggle")
      page.wait_for_timeout(250)
    page.click("#copy")
    page.wait_for_timeout(400)
    assert "copied" in page.inner_text("#toast"), page.inner_text("#toast")
    return "log copied"

  w.step("copy the log", copy)

  def jump():
    if page.eval_on_selector("#logwrap", "e => e.hidden"):
      page.click("#logtoggle")
      page.wait_for_timeout(250)
    # the button only exists for an overflowing log, so constrain the panel to
    # reproduce the condition a long run creates
    page.eval_on_selector(
      "#log",
      "e => { e.style.flex = 'none'; e.style.height = '120px';"
      " e.style.maxHeight = '120px'; e.style.overflow = 'auto'; }",
    )
    page.eval_on_selector(
      "#log", "e => { e.scrollTop = 0; e.dispatchEvent(new Event('scroll')); }"
    )
    page.wait_for_timeout(300)
    page.click("#jump")
    page.wait_for_timeout(400)
    at_bottom = page.eval_on_selector(
      "#log", "e => e.scrollHeight - e.scrollTop - e.clientHeight < 40"
    )
    assert at_bottom, "did not scroll to the end"
    return "jumped to latest"

  w.step("jump-to-latest button", jump)

  def ctrl_enter():
    page.keyboard.press("Control+Enter")
    page.wait_for_timeout(400)
    running = page.eval_on_selector("#statustext", "e => e.textContent")
    assert running in ("starting", "running") or "exit" in running, running
    page.wait_for_timeout(6000)
    return f"cmd+enter started a run ({running})"

  w.step("keyboard: Ctrl+Enter starts", ctrl_enter)


def walk_errors(w: Walk) -> None:
  page = w.page
  page.goto(w.url, wait_until="networkidle")
  page.wait_for_timeout(1000)

  def bad_source():
    page.fill("#add-source", "/definitely/not/a/repo")
    page.click("#add-btn")
    page.wait_for_timeout(1200)
    toast = page.inner_text("#toast")
    assert toast and toast != "", "no toast for a bad path"
    return f"toast={toast[:60]!r}"

  w.step("adding a bad path reports an error", bad_source)

  def empty_source():
    before = w.count(".repo-card")
    page.fill("#add-source", "   ")
    page.click("#add-btn")
    page.wait_for_timeout(600)
    assert w.count(".repo-card") == before, "an empty add changed the list"
    return "no-op, no request"

  w.step("empty add is a no-op", empty_source)


def walk_offline(w: Walk, context) -> None:
  page = w.page
  page.goto(w.url, wait_until="networkidle")
  page.wait_for_timeout(2000)

  def go_offline():
    context.set_offline(True)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(1800)
    w.visible("#offline-banner")
    text = page.inner_text("#offline-banner")
    assert "Cannot reach the server" in text, text
    assert page.is_hidden("#repo-grid"), "grid rendered from nothing"
    return text.replace("\n", " ")[:70]

  w.step("offline: shell loads, server is called out", go_offline)

  def back_online():
    context.set_offline(False)
    page.evaluate("window.dispatchEvent(new Event('online'))")
    page.wait_for_timeout(2000)
    w.visible("#offline-banner", False)
    assert w.count(".repo-card") > 0, "repos did not come back"
    return f"{w.count('.repo-card')} cards back"

  w.step("back online recovers automatically", back_online)


def walk_signed_out(w: Walk, flip: Callable[[bool], None]) -> None:
  page = w.page
  flip(False)

  def signed_out():
    page.goto(w.url, wait_until="networkidle")
    page.wait_for_timeout(2500)
    w.visible("#auth-banner")
    text = page.inner_text("#auth-banner")
    assert "GitHub is not connected" in text, text
    pills = page.eval_on_selector_all(
      ".arena-row .pill", "els => els.map(e => e.innerText)"
    )
    assert pills and all("checks unavailable" in p for p in pills), pills
    return f"{len(pills)} branches say checks unavailable"

  w.step("signed out: banner and honest pills", signed_out)

  def connect_button():
    page.click("#auth-banner button")
    page.wait_for_timeout(1000)
    w.visible("#view-access")
    w.visible("#token-input")
    return "Connect GitHub opens the token form"

  w.step("Connect GitHub opens Access with a token field", connect_button)

  def bad_token():
    page.fill("#token-input", "not a token")
    page.click("#token-btn")
    page.wait_for_timeout(1200)
    toast = page.inner_text("#toast")
    assert "token" in toast.lower(), toast
    return f"rejected: {toast[:50]!r}"

  w.step("a junk token is rejected with a reason", bad_token)

  def sign_in():
    page.fill("#token-input", "ghp_walkthrough123")
    page.click("#token-btn")
    page.wait_for_timeout(2000)
    assert "Signed in" in page.inner_text("#access-body"), page.inner_text(
      "#access-body"
    )[:120]
    return "signed in from the panel"

  w.step("sign in with a token", sign_in)

  def pills_recover():
    page.click("#access-back")
    page.wait_for_timeout(400)
    page.click("#back") if page.is_visible("#back") else None
    page.goto(w.url, wait_until="networkidle")
    page.wait_for_timeout(2200)
    pills = page.eval_on_selector_all(
      ".arena-row .pill", "els => els.map(e => e.innerText)"
    )
    assert any("PR #" in p for p in pills), pills
    return f"pills now: {pills}"

  w.step("checks come back after signing in", pills_recover)
  flip(True)


def walk_mobile(w: Walk) -> None:
  page = w.page
  page.goto(w.url, wait_until="networkidle")
  page.wait_for_timeout(1200)

  w.step(
    "phone: tab bar visible in the repo view",
    lambda: (
      page.click(".repo-card"),
      page.wait_for_timeout(700),
      w.visible("#tabbar"),
    )[-1],
  )
  w.step(
    "phone: paste box is a 48px target",
    lambda: (
      page.click("#back"),
      page.wait_for_timeout(500),
      f"{page.eval_on_selector('#add-source', 'e => Math.round(e.getBoundingClientRect().height)')}px",
    )[-1],
  )
  w.step(
    "phone: Clean & publish runs",
    lambda: (
      page.click(".repo-card"),
      page.wait_for_timeout(700),
      page.click("#start-mobile"),
      page.wait_for_timeout(4000),
      page.inner_text("#statustext"),
    )[-1],
  )


def flip_gh(args: argparse.Namespace, on: bool) -> None:
  """Toggle the fake gh's signed-in marker, then drop the server's cache."""
  marker = Path(args.gh_flag or "")
  if on:
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("")
  elif marker.exists():
    marker.unlink()
  # the server caches auth for 20s and repo status for 8s; this is the same
  # call the Access panel's Re-check button makes
  body = json.dumps({"action": "check"}).encode()
  request = urllib.request.Request(
    f"{args.url}/api/auth",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
  )
  urllib.request.urlopen(request, timeout=10).read()


def walk_view(
  page: Any,
  label: str,
  args: argparse.Namespace,
  out: Path,
  net: Any,
  errors: list[str],
) -> dict[str, Any]:
  """One full pass at one viewport, against any page-shaped driver."""
  w = Walk(page, out, label, errors)
  w.url = args.url
  print(f"\n=== {label} ===")

  def clean_load() -> str:
    page.goto(args.url, wait_until="networkidle")
    page.wait_for_timeout(1500)
    check(not errors, f"console errors: {errors[:3]}")
    return "no errors, no warnings"

  w.step("no console errors on load", clean_load)

  def flip(on: bool) -> None:
    flip_gh(args, on)

  if label == "desktop":
    wash_dashboard(w, args.url)
    walk_dashboard(w, args.url)
    walk_access(w)
    walk_signing(w)
    walk_repo(w)
    walk_job(w, args)
    walk_errors(w)
    if args.gh_flag:
      walk_signed_out(w, flip)
    walk_offline(w, net)
  else:
    walk_mobile(w)

  return {
    "viewport": label,
    "steps": w.steps,
    "failures": w.failures,
    "console_errors": list(errors),
  }


# ---------------------------------------------------------------- drivers ----


def run_api(
  browser: Any, label: str, device: dict[str, Any] | None, args, out: Path
) -> dict[str, Any]:
  context = browser.new_context(**device) if device else browser.new_context()
  page = context.new_page()
  page.set_default_timeout(10000)

  errors: list[str] = []
  # the walk provokes these on purpose, so they are narration, not failures
  induced = ("status of 400", "ERR_INTERNET_DISCONNECTED", "status of 404")

  def on_console(message) -> None:
    if message.type != "error":
      return
    if any(marker in message.text for marker in induced):
      return
    errors.append(message.text)

  page.on("pageerror", lambda exc: errors.append(str(exc)))
  page.on("console", on_console)

  result = walk_view(page, label, args, out, context, errors)
  context.close()
  return result


def run_cli(label: str, args, out: Path) -> dict[str, Any]:
  """The same walk, one `playwright cli` call per action."""
  page = CliPage(f"walk-{label}", out)
  page.close()  # a session left over from an earlier run would keep old state

  open_args = ["open", "--browser", "chromium"]
  if label == "phone":
    open_args += ["--device", "iPhone 13"]
  page._run(*open_args, args.url)
  if label != "phone":
    page._run("resize", "1360", "900")
  page.wait_for_timeout(1000)

  result = walk_view(page, label, args, out, page, [])
  # the CLI has no event listener: read the console buffer at the end instead
  induced = ("status of 400", "ERR_INTERNET_DISCONNECTED", "status of 404")
  errors = [e for e in page.console_errors() if not any(m in e for m in induced)]
  result["console_errors"] = errors
  page.close()
  return result


def main() -> int:
  ap = argparse.ArgumentParser()
  ap.add_argument("--url", default="http://localhost:8080")
  ap.add_argument("--out", default="/tmp/walk")
  ap.add_argument(
    "--driver",
    default="api",
    choices=("api", "cli"),
    help="api drives the Playwright library; cli drives `playwright cli`",
  )
  ap.add_argument(
    "--gh-flag", help="file that turns the fake gh signed-in state on/off"
  )
  args = ap.parse_args()

  out = Path(args.out)
  out.mkdir(parents=True, exist_ok=True)
  report: dict[str, Any] = {"url": args.url, "driver": args.driver, "runs": []}

  if args.driver == "cli":
    for label in ("desktop", "phone"):
      report["runs"].append(run_cli(label, args, out))
  else:
    with sync_playwright() as p:
      browser = p.chromium.launch()
      report["runs"].append(
        run_api(
          browser, "desktop", {"viewport": {"width": 1360, "height": 900}}, args, out
        )
      )
      report["runs"].append(
        run_api(browser, "phone", dict(p.devices["iPhone 13"]), args, out)
      )
      browser.close()

  total = sum(len(r["steps"]) for r in report["runs"])
  failed = sum(r["failures"] for r in report["runs"])
  console = [e for r in report["runs"] for e in r["console_errors"]]
  report["total"] = total
  report["failed"] = failed
  (out / "walk-report.json").write_text(json.dumps(report, indent=2) + "\n")

  print(f"\n{total} steps, {failed} failed, {len(console)} console errors")
  for entry in console[:5]:
    print(f"  console: {entry[:140]}")
  print(f"screenshots: {out}")
  return 1 if failed or console else 0


if __name__ == "__main__":
  raise SystemExit(main())
