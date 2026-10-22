"""Press every control the UI renders, in a real browser, and check each one did something.

The desktop tests share one page and run in file order; the phone tests share
another. Each step drives the app the way a person would. Each asserts a
checkable outcome: a view changed, a request fired, a value appeared.
"""

from __future__ import annotations

import shutil

import pytest

from ..conftest import project_version
from .conftest import Demo, Walker

pytestmark = pytest.mark.e2e

DEMO_REPOS = 3
MIN_TOOLS_READY = 2
MIN_LOG_ROWS = 5
TAP_TARGET_PX = 48
MINUTES_TO_SECONDS = 60
SCROLL_SLACK_PX = 40
needs_gpg = pytest.mark.skipif(
  shutil.which("gpg") is None, reason="the demo has no key without gpg"
)


# -- dashboard ----------------------------------------------------------------


def test_no_console_errors_on_load(desktop: Walker) -> None:
  desktop.goto(1500)
  assert desktop.errors == []


def test_dashboard_renders(desktop: Walker) -> None:
  assert desktop.count(".repo-card") == DEMO_REPOS
  assert "Repositories" in desktop.text(".hero h1")
  assert desktop.text("#ver").strip() == f"v{project_version()}"
  assert desktop.count("#env span.on") >= MIN_TOOLS_READY
  assert desktop.page.get_attribute("#add-source", "placeholder")


def test_typing_into_the_add_box(desktop: Walker) -> None:
  desktop.page.fill("#add-source", "https://github.com/acme/example.git")
  assert desktop.page.input_value("#add-source").endswith("example.git")


def test_open_repo_from_its_card(desktop: Walker) -> None:
  desktop.goto()
  desktop.click(".repo-card", 800)
  assert desktop.visible("#view-repo")
  assert "shop-web" in desktop.text("#repo-title")
  desktop.click("#back", 600)
  assert desktop.visible("#view-dashboard")


def test_card_open_button_opens_the_repo(desktop: Walker) -> None:
  desktop.click(".repo-card .btn.ghost >> nth=0", 700)
  assert desktop.visible("#view-repo")
  desktop.click("#back")


def test_keyboard_enter_on_a_card(desktop: Walker) -> None:
  desktop.page.focus(".repo-card")
  desktop.page.keyboard.press("Enter")
  desktop.page.wait_for_timeout(600)
  assert desktop.visible("#view-repo")
  desktop.click("#back", 400)


# -- access -------------------------------------------------------------------


def test_github_access_panel(desktop: Walker, demo: Demo) -> None:
  desktop.click("#access-btn", 1000)
  assert desktop.visible("#view-access")
  login = demo.api("/api/auth")["gh"]["login"]
  assert f"@{login}" in desktop.text("#access-body .banner.ok")
  body = desktop.text("#access-body")
  assert "repo" in body  # token scopes
  assert ".config/gh/hosts.yml" in body  # the storage card lists the token file
  assert ".gitconfig" in body  # and git's config
  assert desktop.count("#access-body .install-row") == 1


def test_recheck_button_keeps_the_answer(desktop: Walker) -> None:
  desktop.click("text=Re-check", 1200)
  assert desktop.count("#access-body .banner.ok") >= 1
  desktop.click("#access-back")
  assert desktop.visible("#view-dashboard")


# -- signing ------------------------------------------------------------------


def test_signing_panel(desktop: Walker) -> None:
  desktop.click("#signing-btn", 1000)
  assert desktop.visible("#view-signing")
  assert desktop.visible("#gpg-name")
  assert desktop.visible("#gpg-email")
  assert desktop.visible("#signing-body .btn.primary")
  assert desktop.count('a[href="https://github.com/settings/keys"]') == 1


@needs_gpg
def test_signing_panel_lists_the_demo_key(desktop: Walker) -> None:
  assert desktop.count("#signing-body .sign-row") >= 1
  pills = {
    p.strip()
    for p in desktop.page.eval_on_selector_all(
      "#signing-body .pill.ok", "els => els.map(e => e.innerText)"
    )
  }
  # the demo stub lists the key under `gh api user/gpg_keys`, so the panel
  # reports it as assigned and shows no warning
  assert {"active", "on GitHub"} <= pills
  assert desktop.count("#signing-body .banner.ok") >= 1
  assert desktop.count("#signing-body .banner.warn") == 0


def test_back_from_signing(desktop: Walker) -> None:
  desktop.click("#signing-back")
  assert desktop.visible("#view-dashboard")


# -- the repo view ------------------------------------------------------------


def test_sidebar_and_branch_selector(desktop: Walker) -> None:
  desktop.goto(1000)
  desktop.click(".repo-card", 800)
  sidebar = desktop.text("#sidebar")
  assert "Repository" in sidebar
  assert "arena/session-3" in sidebar
  desktop.click('#sidebar [data-branch="arena/session-3"]', 300)
  assert desktop.page.input_value("#branch") == "arena/session-3"
  desktop.page.select_option("#branch", "")
  desktop.page.wait_for_timeout(300)
  assert desktop.page.input_value("#branch") == ""


@pytest.mark.parametrize("command", ["strip", "doctor", "run"])
def test_command_switch(desktop: Walker, command: str) -> None:
  button = f'#cmdswitch button[data-cmd="{command}"]'
  desktop.click(button, 400)
  assert desktop.page.get_attribute(button, "aria-pressed") == "true"


def test_doctor_hides_irrelevant_options(desktop: Walker) -> None:
  desktop.click('#cmdswitch button[data-cmd="doctor"]', 400)
  assert desktop.page.eval_on_selector(
    "#options-card", "e => e.style.display === 'none'"
  )
  desktop.click('#cmdswitch button[data-cmd="run"]', 300)


def test_option_toggle_updates_the_argv(desktop: Walker) -> None:
  toggle = '.toggle[data-opt="dry_run"]'
  desktop.click(toggle, 200)
  assert desktop.page.get_attribute(toggle, "aria-pressed") == "true"
  assert "--dry-run" in desktop.start_argv()
  desktop.click(toggle, 200)
  assert "--dry-run" not in desktop.start_argv()


def test_divergence_segmented_control(desktop: Walker) -> None:
  desktop.click('#divergence button[data-v="remote"]', 200)
  assert "--on-divergence remote" in desktop.start_argv()
  desktop.click('#divergence button[data-v="ask"]', 200)
  assert "--on-divergence" not in desktop.start_argv()


def test_path_chip_add_and_remove(desktop: Walker) -> None:
  desktop.page.fill("#pathin", "uploads")
  desktop.page.press("#pathin", "Enter")
  desktop.page.wait_for_timeout(300)
  assert "--path uploads" in desktop.start_argv()
  assert desktop.count(".chip-x") == 1
  desktop.click(".chip-x button >> nth=0", 300)
  assert "--path" not in desktop.start_argv()


def test_keyboard_backspace_removes_a_chip(desktop: Walker) -> None:
  desktop.page.fill("#pathin", "docs/old.md")
  desktop.page.press("#pathin", "Enter")
  desktop.page.wait_for_timeout(250)
  assert "--path docs/old.md" in desktop.start_argv()
  desktop.page.focus("#pathin")
  desktop.page.keyboard.press("Backspace")
  desktop.page.wait_for_timeout(250)
  assert "--path docs/old.md" not in desktop.start_argv()


def test_timeout_input_drives_check_timeout(desktop: Walker) -> None:
  desktop.page.fill("#timeout", "5")
  desktop.page.dispatch_event("#timeout", "input")
  desktop.page.wait_for_timeout(250)
  assert f"--check-timeout {5 * MINUTES_TO_SECONDS}" in desktop.start_argv()
  desktop.page.fill("#timeout", "15")
  desktop.page.dispatch_event("#timeout", "input")


# -- jobs ---------------------------------------------------------------------


def test_start_a_dry_run_and_watch_it_finish(desktop: Walker) -> None:
  desktop.click('.toggle[data-opt="dry_run"]', 0)
  desktop.click("#start", 0)
  status = desktop.wait_status("exit")
  assert "exit 0" in status
  # the run card is the story; the raw log is one click away
  assert desktop.log_hidden()
  assert desktop.text("#logtoggle") == "Show log"
  desktop.click("#logtoggle", 300)
  assert desktop.text("#logtoggle") == "Hide log"
  assert desktop.count(".log-row") > MIN_LOG_ROWS


def test_cancel_a_run_in_flight(desktop: Walker, demo: Demo) -> None:
  desktop.click("#back")
  desktop.click(".repo-card >> nth=2", 900)
  assert "docs-site" in desktop.text("#repo-title")
  # the demo fixtures finish in a fraction of a second. The stub gh reports a
  # check that never finishes, so the run parks at the PR gate. That is the
  # only place Cancel meets a live process.
  demo.slow_checks(True)
  try:
    toggle = '.toggle[data-opt="dry_run"]'
    if desktop.page.get_attribute(toggle, "aria-pressed") == "true":
      desktop.click(toggle, 150)
    desktop.click("#start", 0)
    desktop.open_log()
    desktop.page.wait_for_function(
      "() => document.querySelector('#log').innerText.includes('still running; waiting up to')",
      timeout=30000,
    )
    assert desktop.visible("#cancel")
    desktop.click("#cancel", 0)
    status = desktop.wait_status("cancelled", timeout=20000)
  finally:
    demo.slow_checks(False)
  assert "cancelled" in status.lower()
  assert not desktop.page.eval_on_selector("#start", "e => e.disabled"), (
    "Start stayed disabled"
  )


def test_copy_the_log(desktop: Walker) -> None:
  desktop.click("#back")
  desktop.click(".repo-card >> nth=0", 800)
  desktop.click('.toggle[data-opt="dry_run"]', 0)
  desktop.click("#start", 0)
  desktop.wait_status("exit")
  desktop.open_log()
  desktop.click("#copy", 400)
  assert "copied" in desktop.text("#toast")


def test_jump_to_latest_button(desktop: Walker) -> None:
  desktop.open_log()
  # the button only exists for an overflowing log, so constrain the panel to
  # reproduce the condition a long run creates
  desktop.page.eval_on_selector(
    "#log",
    "e => { e.style.flex = 'none'; e.style.height = '120px'; e.style.maxHeight = '120px'; e.style.overflow = 'auto'; }",
  )
  desktop.page.eval_on_selector(
    "#log", "e => { e.scrollTop = 0; e.dispatchEvent(new Event('scroll')); }"
  )
  desktop.page.wait_for_timeout(300)
  desktop.click("#jump", 400)
  assert desktop.page.eval_on_selector(
    "#log", f"e => e.scrollHeight - e.scrollTop - e.clientHeight < {SCROLL_SLACK_PX}"
  )


def test_keyboard_ctrl_enter_starts(desktop: Walker) -> None:
  desktop.page.keyboard.press("Control+Enter")
  desktop.page.wait_for_timeout(400)
  running = desktop.status_text()
  assert running in ("starting", "running") or "exit" in running
  desktop.wait_status("exit")


# -- errors -------------------------------------------------------------------


def test_adding_a_bad_path_reports_an_error(desktop: Walker) -> None:
  desktop.goto(1000)
  desktop.page.fill("#add-source", "/definitely/not/a/repo")
  desktop.click("#add-btn", 1200)
  assert desktop.text("#toast").strip()


def test_empty_add_is_a_no_op(desktop: Walker) -> None:
  before = desktop.count(".repo-card")
  desktop.page.fill("#add-source", "   ")
  desktop.click("#add-btn", 600)
  assert desktop.count(".repo-card") == before


# -- signed out ---------------------------------------------------------------


def test_signed_out_banner_and_honest_pills(desktop: Walker, demo: Demo) -> None:
  demo.sign_in(False)
  demo.wait_until_checked(False)
  desktop.goto(2500)
  assert desktop.visible("#auth-banner")
  pills = desktop.page.eval_on_selector_all(
    ".arena-row .pill", "els => els.map(e => e.innerText)"
  )
  assert pills
  assert all("checks unavailable" in p for p in pills), pills


def test_connect_github_opens_access_with_a_token_field(desktop: Walker) -> None:
  desktop.click("#auth-banner button", 1000)
  assert desktop.visible("#view-access")
  assert desktop.visible("#token-input")


def test_a_junk_token_is_rejected(desktop: Walker) -> None:
  desktop.page.fill("#token-input", "not a token")
  desktop.click("#token-btn", 1200)
  assert "token" in desktop.text("#toast").lower()


def test_sign_in_with_a_token(desktop: Walker) -> None:
  desktop.page.fill("#token-input", "ghp_walkthrough123")
  desktop.click("#token-btn", 2000)
  assert desktop.count("#access-body .banner.ok") >= 1


def test_checks_come_back_after_signing_in(desktop: Walker, demo: Demo) -> None:
  desktop.click("#access-back", 400)
  demo.wait_until_checked(True)
  desktop.goto(2200)
  pills = desktop.page.eval_on_selector_all(
    ".arena-row .pill", "els => els.map(e => e.innerText)"
  )
  assert any("PR #" in p for p in pills), pills
  demo.sign_in(True)


# -- offline ------------------------------------------------------------------


def test_offline_shell_loads_and_server_is_called_out(desktop: Walker) -> None:
  desktop.goto(2000)
  desktop.context.set_offline(True)
  desktop.page.reload(wait_until="domcontentloaded")
  desktop.page.wait_for_timeout(1800)
  assert desktop.visible("#offline-banner")
  assert desktop.text("#offline-banner").strip()
  assert desktop.page.is_hidden("#repo-grid"), "grid rendered from nothing"


def test_back_online_recovers_automatically(desktop: Walker) -> None:
  desktop.context.set_offline(False)
  desktop.page.evaluate("window.dispatchEvent(new Event('online'))")
  desktop.page.wait_for_timeout(2000)
  assert not desktop.visible("#offline-banner")
  assert desktop.count(".repo-card") == DEMO_REPOS
  assert desktop.errors == []


# -- phone --------------------------------------------------------------------


def test_phone_loads_without_console_errors(phone: Walker) -> None:
  phone.goto(1500)
  assert phone.errors == []


def test_phone_tab_bar_in_the_repo_view(phone: Walker) -> None:
  phone.click(".repo-card", 700)
  assert phone.visible("#tabbar")


def test_phone_paste_box_is_a_tap_target(phone: Walker) -> None:
  phone.click("#back")
  height = phone.page.eval_on_selector(
    "#add-source", "e => Math.round(e.getBoundingClientRect().height)"
  )
  assert height >= TAP_TARGET_PX


def test_phone_clean_and_publish_runs(phone: Walker) -> None:
  phone.click(".repo-card", 700)
  phone.click("#start-mobile", 4000)
  assert phone.status_text().strip()
  assert phone.errors == []
