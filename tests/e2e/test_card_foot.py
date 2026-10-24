"""Every card action sits bottom right in a card foot, at both widths.

nuu puts the close x top right and every other action button bottom right.
The run button, two Save buttons, and GitHub and signing actions
all live in a `.card-foot` row. The phone keeps its tab
bar as the run control, so the options foot hides there.
"""

from __future__ import annotations

import pytest

from scripts.walk import Walker

pytestmark = pytest.mark.e2e

CARD = ".repo-card:has-text('shop-web') .repo-name"
CARD_PAD = 16
BORDER = 1
FEET = """() => {
  const r = (e) => e.getBoundingClientRect();
  return [...document.querySelectorAll('.card-foot')]
    .filter((f) => f.getClientRects().length > 0)
    .map((f) => {
      const card = f.closest('.card');
      const buttons = [...f.querySelectorAll('.btn')];
      return {
        card: card.id,
        cardRight: r(card).right,
        cardBottom: r(card).bottom,
        footBottom: r(f).bottom,
        lastRight: r(buttons[buttons.length - 1]).right,
        rights: buttons.map((b) => r(b).right),
        labels: buttons.map((b) => b.textContent.trim()),
      };
    });
}"""
SETTINGS_FEET = {
  "card-identity": ["Save"],
  "card-claims": ["Save"],
  "card-github": ["Re-check"],
  "card-create-key": ["Create key"],
  "card-github-keys": ["Re-check", "Open GitHub keys"],
}


def feet_on(walker: Walker, hash_route: str) -> dict[str, dict]:
  page = walker.page
  page.goto(f"{walker.url}/{hash_route}", wait_until="networkidle")
  if hash_route:
    page.wait_for_selector("#card-identity")
  else:
    page.wait_for_selector(".repo-card")
    walker.click(CARD, 800)
    page.wait_for_selector("#options-card")
  page.wait_for_timeout(300)
  return {foot["card"]: foot for foot in page.evaluate(FEET)}


def assert_bottom_right(foot: dict) -> None:
  inset = CARD_PAD + BORDER
  assert foot["lastRight"] == pytest.approx(foot["cardRight"] - inset, abs=0.5), foot
  assert foot["footBottom"] == pytest.approx(foot["cardBottom"] - BORDER, abs=0.5), foot
  assert foot["rights"] == sorted(foot["rights"]), foot


@pytest.mark.parametrize("width", ["desktop", "phone"])
def test_the_settings_actions_sit_bottom_right(
  request: pytest.FixtureRequest, width: str
) -> None:
  walker: Walker = request.getfixturevalue(width)
  feet = feet_on(walker, "#/settings")
  assert {k: v["labels"] for k, v in feet.items()} == SETTINGS_FEET
  for foot in feet.values():
    assert_bottom_right(foot)


def test_the_run_button_sits_in_the_options_foot(desktop: Walker) -> None:
  feet = feet_on(desktop, "")
  assert feet["options-card"]["labels"] == ["Clean & Push"]
  assert_bottom_right(feet["options-card"])
  assert desktop.count("#options-card .card-head .btn") == 0


def test_the_phone_keeps_the_tab_bar_as_the_run_control(phone: Walker) -> None:
  feet = feet_on(phone, "")
  assert "options-card" not in feet
  assert phone.visible("#start-mobile")
