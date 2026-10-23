"""The page's feedback: the offline banner, the phase list, and the add bar."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from scripts.walk import Walker

REPOS_API = "**/api/repos"


@pytest.fixture
def offline(desktop: Walker) -> Iterator[Walker]:
  desktop.page.route(REPOS_API, lambda route: route.abort())
  yield desktop
  desktop.page.unroute(REPOS_API)


def test_the_offline_banner_puts_retry_on_its_own_line(offline: Walker) -> None:
  offline.goto(800)
  assert offline.visible("#offline-banner #retry")
  lines = offline.text("#offline-banner").strip().splitlines()
  assert lines[0].endswith("then retry.") and lines[-1] == "Retry"
  lead = offline.page.eval_on_selector(
    "#offline-banner b", "e => e.getBoundingClientRect().bottom"
  )
  button = offline.page.eval_on_selector("#retry", "e => e.getBoundingClientRect().top")
  assert button >= lead, "the button shares a line with the text"


def test_a_failed_pr_check_fails_the_pr_phase_alone(desktop: Walker) -> None:
  desktop.goto(1200)
  desktop.click(".repo-card:has-text('billing-api')", 800)
  desktop.click('input[data-opt="dry_run"]', 0)
  desktop.click("#start", 0)
  assert "exit 0" not in desktop.wait_status("exit")
  states = desktop.page.eval_on_selector_all(
    ".phase", "els => els.map((e) => [e.dataset.phase, e.dataset.state])"
  )
  assert dict(states) == {
    "prepare": "done",
    "pr": "fail",
    "rewrite": "skip",
    "publish": "skip",
    "sync": "skip",
  }


def test_the_add_bar_reports_a_bad_source_under_the_field(desktop: Walker) -> None:
  desktop.goto(1200)
  page = desktop.page
  page.fill("#add-source", "not a url")
  desktop.click("#add-btn", 200)
  assert page.is_visible("#add-error")
  assert page.get_attribute("#add-source", "aria-invalid") == "true"
  assert page.get_attribute("#add-source", "aria-describedby") == "add-error"
  assert page.eval_on_selector("#toast", "e => e.classList.contains('show')") is False
  page.type("#add-source", "x")
  assert page.is_hidden("#add-error")
  assert page.get_attribute("#add-source", "aria-invalid") is None


def test_the_log_stays_open_and_copy_is_a_glyph(desktop: Walker) -> None:
  desktop.goto(1200)
  desktop.click(".repo-card", 800)
  page = desktop.page
  assert page.get_by_role("button", name="Reload commits").count() == 1
  assert page.inner_text("#commits-refresh") == ""
  assert page.get_by_role("button", name="Copy log").count() == 1
  assert page.inner_text("#copy") == ""
  assert page.locator("#logtoggle").count() == 0
  assert page.is_visible("#logwrap")
  assert page.locator("#log .log-row").count() == 0
  placeholder = "e => getComputedStyle(e, '::before').content"
  assert page.eval_on_selector("#log", placeholder) != "none"
  desktop.click('input[data-opt="dry_run"]', 0)
  desktop.click("#start", 0)
  desktop.wait_status("exit")
  assert page.locator("#log .log-row").count() > 0
  assert page.eval_on_selector("#log", placeholder) == "none"


LONG_SUBJECT = ".commit:has-text('fixed sleep in the flaky config timing test')"


def test_a_long_subject_clamps_to_two_lines_until_a_tap(phone: Walker) -> None:
  phone.goto(1200)
  phone.click(".repo-card", 800)
  page = phone.page
  subject = f"{LONG_SUBJECT} .subject"
  line = page.eval_on_selector(
    subject, "e => parseFloat(getComputedStyle(e).lineHeight)"
  )
  shown = page.eval_on_selector(subject, "e => e.getBoundingClientRect().height")
  assert line < shown <= 2 * line + 1, (line, shown)
  assert page.get_attribute(LONG_SUBJECT, "aria-expanded") == "false"
  phone.click(LONG_SUBJECT, 200)
  assert page.get_attribute(LONG_SUBJECT, "aria-expanded") == "true"
  whole = page.eval_on_selector(subject, "e => e.getBoundingClientRect().height")
  assert whole > 2 * line + 1, (line, whole)  # the clamp did cut a third line
  phone.click(LONG_SUBJECT, 200)
  assert page.get_attribute(LONG_SUBJECT, "aria-expanded") == "false"
  assert (
    page.eval_on_selector(subject, "e => e.getBoundingClientRect().height") == shown
  )


SIGNING_API = "**/api/signing"


def test_every_banner_leads_with_its_glyph(desktop: Walker) -> None:
  desktop.page.route(SIGNING_API, lambda route: route.abort())
  try:
    desktop.page.goto(desktop.url.rstrip("/") + "/#/settings")
    desktop.page.wait_for_selector("#signing-body .banner.err", timeout=8000)
  finally:
    desktop.page.unroute(SIGNING_API)
  banners = desktop.page.eval_on_selector_all(
    ".banner", "els => els.map((e) => [e.className, !!e.querySelector('svg')])"
  )
  assert len(banners) >= 2
  assert all(has_glyph for _, has_glyph in banners), banners
