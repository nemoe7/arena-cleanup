"""Every button that leads to GitHub carries the GitHub mark, and its label drops the word."""

from __future__ import annotations

import pytest

from scripts.walk import Demo, Walker

pytestmark = pytest.mark.e2e

BILLING = ".repo-card:has-text('billing-api')"
# the mark is the one Octicon, drawn on a 16 px grid, where Lucide draws on 24
MARKED = """(sel) => {
  const el = document.querySelector(sel);
  const svg = el.querySelector('.ico-svg svg');
  return [svg ? svg.getAttribute('viewBox') : null, el.innerText.trim(), el.title];
}"""


def marked(walker: Walker, sel: str) -> list[str]:
  walker.page.wait_for_selector(sel)
  return walker.page.evaluate(MARKED, sel)


def test_the_checks_modal_links_lead_with_the_mark(desktop: Walker) -> None:
  page = desktop.page
  desktop.goto(1200)
  page.click(f"{BILLING} button.pill")
  page.wait_for_selector("#checks-modal[open]")
  try:
    assert marked(desktop, "#checks-pr") == [
      "0 0 16 16",
      "Open PR",
      "Open PR on GitHub",
    ]
    page.click("#checks-list li:has-text('test') .check-row")
    assert marked(desktop, "#checks-list li.open .job-pane a.btn") == [
      "0 0 16 16",
      "Open",
      "Open on GitHub",
    ]
  finally:
    page.keyboard.press("Escape")
    page.wait_for_function("!document.getElementById('checks-modal').open")


def test_the_phase_modal_link_leads_with_the_mark(desktop: Walker) -> None:
  desktop.goto(1200)
  assert desktop.page.evaluate(
    "() => [document.querySelector('#phase-link .ico-svg svg').getAttribute('viewBox'),"
    " document.getElementById('phase-link').textContent.trim()]"
  ) == ["0 0 16 16", "Open"]


def test_the_signed_out_banner_offers_connect_with_the_mark(
  desktop: Walker, demo: Demo
) -> None:
  demo.sign_in(False)
  demo.wait_until_checked(False)
  try:
    desktop.goto(2500)
    assert marked(desktop, "#auth-banner button") == [
      "0 0 16 16",
      "Connect",
      "Connect GitHub",
    ]
  finally:
    demo.sign_in(True)
    demo.wait_until_checked(True)


def test_the_key_card_opens_the_keys_page_with_the_mark(desktop: Walker) -> None:
  desktop.page.goto(f"{desktop.url}/#/settings", wait_until="networkidle")
  assert marked(desktop, "#card-github-keys a.btn") == [
    "0 0 16 16",
    "Open keys",
    "Open GitHub keys",
  ]
