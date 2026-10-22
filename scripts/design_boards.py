#!/usr/bin/env python3
"""Render the design boards under docs/design/ from the live stylesheet.

The boards follow the documentation set of the uiprep article. They show the
lay of the land, a deep-dive wireframe, example views, and component states.
Three more show the global components, the style guide, and do and do-not pairs.

Every board is HTML built from the app's own tokens, classes, and glyphs. The
example views are screenshots of a demo instance.

  uv run scripts/design_boards.py                       # writes docs/design/*.png
  uv run scripts/design_boards.py --out /tmp/boards --chromium /path/to/chrome

It needs Playwright: `uv sync --group qa`, then `uv run playwright install
chromium`, or `--chromium` with a Chromium binary of your own.
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.walk import DESKTOP, ROOT, Demo, Walker, launch_browser

INDEX = ROOT / "ui" / "static" / "index.html"
OUT = ROOT / "docs" / "design"
BOARD_WIDTH = 1600
ICONS_RE = re.compile(r"(const svg = .*?\n  const ICONS = \{.*?\n  \};)", re.DOTALL)
FILL_SLOTS = (
  'for (const slot of document.querySelectorAll("[data-icon]")) '
  'slot.innerHTML = ICONS[slot.dataset.icon] || "";'
)

COLOURS = [
  ("bg", "#08090b", "page"),
  ("surface", "#0d0f12", "cards"),
  ("surface-2", "#12151a", "fields, pills, buttons"),
  ("surface-3", "#171b21", "hover, wireframe blocks"),
  ("line", "#1b1f25", "card borders, row rules"),
  ("line-2", "#262c34", "control borders"),
  ("text", "#e9ebee", "body text"),
  ("muted", "#9ba2ab", "secondary text"),
  ("dim", "#7d858f", "hints, metadata"),
  ("accent", "#6e79d6", "primary button"),
  ("accent-hi", "#868ff0", "hover, focus, running"),
  ("ok", "#46b95c", "passed, signed in"),
  ("warn", "#d6a032", "needs attention"),
  ("err", "#f0574f", "failed, missing"),
  ("info", "#5aa2f7", "running checks"),
]
DESKTOP_RAMP = [
  ("--fs-1", "12 px", "metadata, mono details"),
  ("--fs-2", "13 px", "controls, labels"),
  ("--fs-3", "14 px", "body, names, buttons"),
  ("--fs-4", "16 px", "view title"),
  ("--fs-5", "20 px", "page title"),
]
PHONE_RAMP = "12, 13, 14, 15 body, 16 fields, 19 title at 720 px and below"
SPACING = [2, 4, 6, 8, 10, 12, 16, 20, 24, 32]
RADII = [
  ("12 px", "cards"),
  ("8 px", "buttons, fields, banners"),
  ("6 px", "chips"),
  ("999 px", "pills"),
]
PHASE_ICON = {
  "idle": "circle-small",
  "run": "loader-circle",
  "done": "check",
  "fail": "x",
  "skip": "minus",
}

BOARD_CSS = """
/* frozen motion keeps a board byte-identical between runs */
.board *, .board *::before, .board *::after { animation: none !important; transition: none !important; }
.board { padding: 32px; background: var(--bg); color: var(--text); font-family: var(--sans);
  width: max-content; max-width: 1536px; }
.board h1 { font-size: var(--fs-5); font-weight: 640; margin: 0 0 4px; }
.board .lede { color: var(--muted); font-size: var(--fs-2); margin: 0 0 24px; max-width: 720px; }
.board .row { display: flex; gap: 24px; align-items: flex-start; flex-wrap: wrap; }
.board .col { display: flex; flex-direction: column; gap: 10px; align-items: flex-start; }
.board .frame { border: 1px solid var(--line); border-radius: 12px; background: var(--surface); padding: 16px; }
.board .lbl { font-size: var(--fs-2); font-weight: 600; margin: 0 0 2px; }
.board .sub { font-size: var(--fs-1); color: var(--dim); margin: 0 0 10px; max-width: 320px; line-height: 1.45; }
.board .cap { font-size: var(--fs-1); color: var(--dim); margin-top: 8px; }
.board img { display: block; border: 1px solid var(--line-2); border-radius: 8px; }
.board table.sheet { border-collapse: collapse; font-size: var(--fs-2); }
.board table.sheet td { padding: 6px 12px 6px 0; vertical-align: middle; }
.board .mono { font-family: var(--mono); font-size: var(--fs-1); color: var(--muted); }
.board .swatch { width: 72px; height: 28px; border-radius: 6px; border: 1px solid var(--line-2); }
.board .sbar { height: 10px; background: var(--accent); border-radius: 2px; }
.board .rbox { width: 72px; height: 48px; border: 1px solid var(--line-2); background: var(--surface-2); }
.board .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.board .verdict { display: flex; align-items: center; gap: 6px; font-size: var(--fs-1); font-weight: 600;
  margin-bottom: 8px; }
.board .verdict.do { color: #8fe0a0; }
.board .verdict.dont { color: #ff9a94; }
.board .off { display: flex; gap: 7px; align-items: center; }
.board .glyph { font-size: 15px; line-height: 1; }
.board .narrow { width: 328px; }
.board .phases { list-style: none; margin: 0; padding: 0; }
.wf .scr { width: 300px; border: 1px solid var(--line-2); border-radius: 8px; background: var(--surface);
  padding: 10px; display: flex; flex-direction: column; gap: 8px; }
.wf .scr.wide { width: 420px; }
.wf .blk { background: var(--surface-3); border-radius: 6px; min-height: 12px; }
.wf .blk.hi { background: var(--accent); }
.wf .blk.soft { background: var(--surface-2); border: 1px dashed var(--line-2); }
.wf .blk.lbl { display: flex; align-items: center; justify-content: center; font-size: var(--fs-1);
  color: var(--muted); padding: 6px 8px; }
.wf .blk.lbl.hi { color: #fff; }
.wf .bar { display: flex; gap: 6px; align-items: center; }
.wf .arrow { align-self: center; color: var(--dim); font-size: var(--fs-1); display: flex; flex-direction: column;
  align-items: center; gap: 4px; padding: 0 4px; width: 92px; text-align: center; }
.wf .arrow b { font-size: 18px; color: var(--muted); }
"""

HEAD = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<base href="{base}/"><style>{css}</style><style>{board}</style></head><body>{body}
<script>{{ {icons}
{fill} }}</script></body></html>"""


def app_css() -> str:
  html = INDEX.read_text()
  match = re.search(r"<style>(.*?)</style>", html, re.DOTALL)
  if not match:
    raise RuntimeError("no <style> block in index.html")
  return match.group(1)


def icon_script() -> str:
  """The ICONS table of index.html, so the boards draw the app's own glyphs."""
  match = ICONS_RE.search(INDEX.read_text())
  if not match:
    raise RuntimeError("no ICONS table in index.html")
  return match.group(1)


def icon(name: str, cls: str = "ico-svg") -> str:
  return f'<span class="{cls}" data-icon="{name}" aria-hidden="true"></span>'


def pill(variant: str, text: str, dot: bool = True) -> str:
  cls = f"pill {variant}".strip()
  lead = '<i class="dot"></i>' if dot else ""
  return f'<span class="{cls}">{lead}{text}</span>'


def banner(variant: str, text: str, glyph: str = "triangle-alert") -> str:
  return (
    f'<div class="banner {variant}" style="max-width:420px"><span class="ico">{icon(glyph)}</span>'
    f"<div>{text}</div></div>"
  )


def card(title: str, body: str, hint: str = "") -> str:
  hint_html = f'<span class="hint">{hint}</span>' if hint else ""
  return (
    '<div class="card" style="width:420px">'
    f'<div class="card-head"><h2>{title}</h2><div class="grow"></div>{hint_html}</div>'
    f'<div class="card-body">{body}</div></div>'
  )


def check(label: str, on: bool, danger: bool = False) -> str:
  cls = "check danger" if danger else "check"
  checked = " checked" if on else ""
  return f'<label class="{cls}"><input type="checkbox"{checked}>{label}</label>'


def phase(state: str, name: str, sub: str, time: str) -> str:
  cls = "ico-svg idle" if state == "idle" else "ico-svg"
  return (
    f'<li class="phase" data-state="{state}"><div class="phase-head">'
    f'<span class="phase-ico">{icon(PHASE_ICON[state], cls)}</span><span class="phase-name">{name}</span>'
    f'<span class="phase-sub">{sub}</span><span class="phase-time">{time}</span>'
    "</div></li>"
  )


def status(variant: str, text: str) -> str:
  return f'<span class="status {variant}"><span class="led"></span>{text}</span>'


def block(
  label: str = "",
  hi: bool = False,
  soft: bool = False,
  height: int = 0,
  width: str = "",
) -> str:
  cls = (
    "blk"
    + (" hi" if hi else "")
    + (" soft" if soft else "")
    + (" lbl" if label else "")
  )
  style = ";".join(
    s
    for s in (f"height:{height}px" if height else "", f"width:{width}" if width else "")
    if s
  )
  return f'<div class="{cls}" style="{style}">{label}</div>'


def frame(title: str, sub: str, body: str) -> str:
  return f'<div class="col"><div><p class="lbl">{title}</p><p class="sub">{sub}</p></div>{body}</div>'


def board(title: str, lede: str, body: str, extra_class: str = "") -> str:
  return f'<div class="board {extra_class}"><h1>{title}</h1><p class="lede">{lede}</p>{body}</div>'


def img(shots: dict[str, bytes], name: str, width: int) -> str:
  data = base64.b64encode(shots[name]).decode()
  return (
    f'<img src="data:image/png;base64,{data}" style="width:{width}px" alt="{name}">'
  )


# -- boards -------------------------------------------------------------------


def flow_board(_: dict[str, bytes]) -> str:
  topbar = (
    '<div class="bar">'
    + block("arena-cleanup", width="110px")
    + '<div class="grow"></div>'
    + block(height=22, width="22px")
    + "</div>"
  )
  dashboard = (
    '<div class="scr wide">'
    + topbar
    + block("Repos", width="90px")
    + '<div class="bar">'
    + block("paste a GitHub URL or a path", soft=True, width="300px")
    + block("Add", hi=True, width="60px")
    + '</div><div class="bar">'
    + "".join(block("repo card", height=84, width="128px") for _ in range(3))
    + "</div></div>"
  )
  repo = (
    '<div class="scr wide">'
    + '<div class="bar">'
    + block(icon("arrow-left") + "&nbsp;All repos", width="100px")
    + block("shop-web", width="80px")
    + "</div>"
    + '<div class="bar" style="align-items:flex-start">'
    + block("facts · arena branches · commits", height=150, width="110px")
    + '<div class="col" style="gap:8px;flex:1">'
    + block("options card", height=60, width="300px")
    + block("run card: 5 phases, log", hi=True, height=56, width="300px")
    + "</div></div></div>"
  )
  settings = (
    '<div class="scr">'
    + '<div class="bar">'
    + block(icon("arrow-left") + "&nbsp;Back", width="70px")
    + block("Settings", width="100px")
    + "</div>"
    + block("identity · name · e-mail", height=24)
    + block("GitHub access · signed in as @you", height=24)
    + block("commit signing · keys · create", height=24)
    + block("claimed commits · emails · names", height=24)
    + block("about", height=24)
    + "</div>"
  )

  def arrow(text: str) -> str:
    return f'<div class="arrow"><b>{icon("chevron-right")}</b>{text}</div>'

  body = (
    '<div class="wf"><div class="row" style="align-items:center">'
    + frame(
      "Dashboard", "Entry at /. Every remembered repository is one card.", dashboard
    )
    + arrow("card click or Enter")
    + frame(
      "Repository",
      "Options, the run, and the commits. Back returns to the dashboard.",
      repo,
    )
    + '</div><div class="row" style="margin-top:24px;align-items:center">'
    + '<div class="col" style="width:420px"></div>'
    + arrow("gear icon, from either view")
    + frame(
      "Settings",
      "Identity, GitHub access, signing, and the claim rules; then About.",
      settings,
    )
    + "</div></div>"
  )
  return board(
    "Lay of the land",
    "The three views and how a person moves between them. Blocks stand for regions, "
    "the accent block for the primary action of the view.",
    body,
  )


def wireframe_board(_: dict[str, bytes]) -> str:
  options = (
    block("Options ▾ — main (default) · defaults", height=28)
    + block("Target branch | main (default)", height=28)
    + block("Arena branch | newest first, with two or more", height=28)
    + block("Remove paths | one chip per path | Browse", height=28)
    + block("HEAD tree — folders first, a click adds the chip", height=28)
    + block("PR check timeout | slider, 0 to 120 min | 15 min", height=28)
    + '<div class="bar" style="flex-wrap:wrap">'
    + "".join(
      block(t, height=24, width="auto")
      for t in (
        "☐ Dry Run",
        "☐ Ignore PR Checks",
        "☐ Keep Empty Commits",
        "☑ Update Tags",
        "☐ Force Push",
      )
    )
    + "</div>"
  )
  run = (
    '<div class="bar">'
    + block("● idle", width="60px")
    + '<div class="grow"></div>'
    + block("Clean & Push", hi=True, width="120px")
    + block("Cancel", width="60px")
    + "</div>"
    + "".join(
      block(f"{n} — {s}", height=24)
      for n, s in (
        ("Prepare", "fetch, branches, checkout"),
        ("PR checks", "read the pull request"),
        ("Rewrite and sign", "claim, trim, sign"),
        ("Publish", "push, tags, cleanup"),
        ("Finish", "back to the default branch"),
      )
    )
    + '<div class="bar">'
    + block("Show log", width="70px")
    + '<div class="grow"></div>'
    + block("Copy log", width="70px")
    + "</div>"
  )
  sidebar = (
    block("Repo — branch · default", height=24)
    + block("Arena branches — ↑ N · PR", height=24)
    + block("Commits — 1 of 1 · Reload", height=24)
    + block("6f5a842  chore: init", height=24)
  )
  screen = (
    '<div class="scr wide" style="width:560px">'
    + '<div class="bar">'
    + block(icon("arrow-left") + "&nbsp;All repos", width="100px")
    + block("shop-web", width="90px")
    + "</div>"
    + '<div class="bar" style="align-items:flex-start">'
    + f'<div class="scr" style="width:220px">{sidebar}</div>'
    + '<div class="col" style="gap:8px;flex:1">'
    + f'<div class="scr" style="width:auto">{options}</div>'
    + f'<div class="scr" style="width:auto">{run}</div>'
    + "</div></div></div>"
  )
  actions = (
    '<table class="sheet"><tr><td class="mono">Clean &amp; Push</td>'
    "<td>starts the run with the options shown</td></tr>"
    '<tr><td class="mono">Cancel</td><td>terminates the child process; the log says cancelled</td></tr>'
    '<tr><td class="mono">Show log</td><td>unfolds the raw lines under the phase list</td></tr>'
    '<tr><td class="mono">Copy log</td><td>puts the whole log on the clipboard</td></tr>'
    '<tr><td class="mono">Ctrl + Enter</td><td>starts the run from anywhere</td></tr>'
    '<tr><td class="mono">980 px</td><td>the sidebar stacks below the run card</td></tr>'
    '<tr><td class="mono">720 px</td><td>primary actions stick to the bottom; one column</td></tr></table>'
  )
  body = (
    '<div class="wf"><div class="row">'
    + frame(
      "Repository view",
      "Deep dive: the one view where a run happens. The sidebar holds the facts and the "
      "commits; the run card is the story, the raw log is one click away.",
      screen,
    )
    + frame("Key actions", "What the view promises.", actions)
    + "</div></div>"
  )
  return board(
    "Repository view", "Deep-dive wireframe of the view a run lives in.", body
  )


def views_board(shots: dict[str, bytes]) -> str:
  body = (
    '<div class="row">'
    + frame(
      "Default view",
      "Five remembered repositories, the add bar focused, the tool dots green.",
      img(shots, "dashboard", 460),
    )
    + frame(
      "Signed out",
      "The banner offers Connect GitHub. Every arena row reads checks unavailable, never no PR.",
      img(shots, "signed-out", 460),
    )
    + frame(
      "After a run",
      "Five phases with their results and times; the raw log unfolded.",
      img(shots, "after-run", 460),
    )
    + frame(
      "Settings",
      "Identity, GitHub access, signing, and the claim rules, then the informing cards.",
      img(shots, "settings", 460),
    )
    + "</div>"
  )
  return board(
    "Example views",
    "Full views at 1360 px, straight from the demo fixture. "
    "A new view is only documented when an event changes the whole page.",
    body,
  )


def states_board(_: dict[str, bytes]) -> str:
  run_states = (
    '<table class="sheet">'
    f"<tr><td>{status('', 'idle')}</td><td>before Start; the phase list is grey</td></tr>"
    f"<tr><td>{status('running', 'running')}</td><td>the LED pulses; Cancel is enabled</td></tr>"
    f"<tr><td>{status('ok', 'exit 0')}</td><td>every phase done; the log stays folded</td></tr>"
    f"<tr><td>{status('fail', 'exit 1')}</td><td>the failing phase is red; the log opens</td></tr>"
    f"<tr><td>{status('fail', 'cancelled')}</td><td>Cancel pressed; distinct from a crash</td></tr>"
    "</table>"
  )
  phases = (
    '<ul class="phases card" style="width:420px">'
    + phase("done", "Prepare", "fetch, branches, checkout", "0.4s")
    + phase(
      "run", "PR checks", 'check "ci": still running; waiting up to 15 min', "running"
    )
    + phase("idle", "Rewrite and sign", "claim, trim, sign", "")
    + phase("skip", "Publish", "skipped: dry run", "")
    + phase("fail", "Finish", "working tree has 1 uncommitted change", "<0.1s")
    + "</ul>"
  )
  pr_pills = (
    '<table class="sheet">'
    f"<tr><td>{pill('ok', 'PR #142, 4/4')}</td><td>open pull request, all checks passed</td></tr>"
    f"<tr><td>{pill('err', 'PR #88, 1/3')}</td><td>a check failed; the run stops at the gate</td></tr>"
    f"<tr><td>{pill('run', 'PR #12, 2/3')}</td><td>checks still running; the run waits</td></tr>"
    f"<tr><td>{pill('mono', 'no PR', dot=False)}</td><td>the branch exists, no open pull request</td></tr>"
    f"<tr><td>{pill('warn', 'checks unavailable', dot=False)}</td><td>signed out: the app cannot know</td></tr>"
    "</table>"
  )
  body = (
    '<div class="row">'
    + frame("Run status", "The pill in the run card head.", run_states)
    + frame(
      "Phase rows",
      "One row per phase; the glyph and its colour are the state.",
      phases,
    )
    + frame(
      "Arena row pills", "On every dashboard card, one per arena branch.", pr_pills
    )
    + "</div>"
  )
  return board(
    "Component states",
    "States of the components that belong to the run and the dashboard, next to the views they appear in.",
    body,
  )


def components_board(_: dict[str, bytes]) -> str:
  buttons = (
    '<table class="sheet">'
    '<tr><td>primary</td><td><button class="btn primary">Clean &amp; Push</button></td>'
    '<td><button class="btn primary" disabled>Clean &amp; Push</button></td></tr>'
    '<tr><td>default</td><td><button class="btn">Reload</button></td>'
    '<td><button class="btn" disabled>Reload</button></td></tr>'
    '<tr><td>ghost</td><td><button class="btn ghost">Re-check</button></td>'
    '<td><button class="btn ghost" disabled>Re-check</button></td></tr>'
    f'<tr><td>back</td><td><button class="btn ghost back">{icon("arrow-left")}All repos</button></td><td></td></tr>'
    f'<tr><td>icon</td><td><button class="icon-btn" aria-label="Settings">{icon("settings")}</button></td>'
    "<td></td></tr>"
    '<tr><td></td><td class="mono">default</td><td class="mono">disabled</td></tr></table>'
  )
  pills = (
    '<div class="col">'
    + '<div class="row" style="gap:8px">'
    + pill("mono", "main", dot=False)
    + pill("", "clean", dot=False)
    + pill("mono ahead", f"{icon('arrow-up')}23", dot=False)
    + pill("ok", "clean")
    + pill("err", "failing")
    + pill("run", "running")
    + pill("mono", "6f5a842", dot=False)
    + "</div>"
    + '<div class="row" style="gap:8px"><span class="chip">0.1.0</span>'
    + f'<span class="chip-x">uploads/ <button aria-label="remove">{icon("x")}</button></span></div></div>'
  )
  fields = (
    '<div class="col" style="width:320px"><input class="field" placeholder="Paste a repo URL…">'
    '<input class="field" value="https://github.com/acme/example.git">'
    '<input class="field" value="disabled" disabled>'
    '<select class="field"><option>main (default)</option></select></div>'
  )
  checks = (
    '<div class="checks">'
    + check("Dry Run", False)
    + check("Dry Run", True)
    + check("Force Push", True, danger=True)
    + "</div>"
  )
  banners = (
    '<div class="col">'
    + banner("ok", "<b>Signed in as @demo</b> on github.com.", "check")
    + banner(
      "warn",
      "<b>This key is not assigned to your GitHub account.</b> Commits will show as Unverified.",
    )
    + banner(
      "err",
      "<b>Cannot reach the server.</b> Check that the container is running, then retry.",
    )
    + "</div>"
  )
  cards = card(
    "Keys in this container",
    '<div class="sign-row"><div class="sign-key"><b>Demo User &lt;demo@example.com&gt;</b>'
    '<div class="mono">3AA5 C34D 7F2B 1C4E</div></div>'
    + pill("ok", "active")
    + "</div>",
    "1 found",
  )
  body = (
    '<div class="row">'
    + frame(
      "Buttons",
      "34 px high, 8 px radius; 44 px on a phone. Hover lifts the surface one step.",
      buttons,
    )
    + frame(
      "Pills and chips",
      "Pills carry a dot or a glyph and a word; mono pills carry names and hashes. Chips are inert; chip-x removes.",
      pills,
    )
    + frame(
      "Fields",
      "34 px, surface-2, a 3 px accent-soft ring on focus. 16 px text on a phone.",
      fields,
    )
    + '</div><div class="row" style="margin-top:24px">'
    + frame(
      "Checkboxes", "Off, on, and the warn colour for a destructive option.", checks
    )
    + frame("Banners", "A bold lead, one sentence of action; ok, warn, err.", banners)
    + frame(
      "Cards", "12 px radius, 1 px line, a 44 px head with an optional hint.", cards
    )
    + "</div>"
  )
  return board(
    "Global components",
    "Every component that is not tied to one view. All variants shown are in use.",
    body,
  )


def style_board(_: dict[str, bytes]) -> str:
  ramp = (
    '<table class="sheet">'
    + "".join(
      f'<tr><td class="mono">{tok}</td><td class="mono">{size}</td>'
      f'<td style="font-size:var({tok})">The quick brown fox jumps over the lazy dog</td>'
      f'<td class="mono">{use}</td></tr>'
      for tok, size, use in DESKTOP_RAMP
    )
    + (
      '<tr><td class="mono">--mono</td><td class="mono">12 px</td>'
      '<td class="mono" style="color:var(--text)">git push --force-with-lease origin main</td>'
      '<td class="mono">paths, hashes</td></tr>'
      f'</table><p class="cap">Inter 400, 520 to 640, 600 for headings. Phone ramp: {PHONE_RAMP}.</p>'
    )
  )
  palette = (
    '<table class="sheet">'
    + "".join(
      f'<tr><td><div class="swatch" style="background:{hex_}"></div></td>'
      f'<td class="mono" style="color:var(--text)">--{name}</td>'
      f'<td class="mono">{hex_}</td><td class="mono">{use}</td></tr>'
      for name, hex_, use in COLOURS
    )
    + "</table>"
  )
  surfaces = (
    '<div style="background:var(--bg);padding:16px;border:1px solid var(--line);border-radius:12px;width:320px">'
    '<div class="card" style="padding:12px"><p class="sub" style="margin:0 0 8px">surface + line</p>'
    '<div style="background:var(--surface-2);border:1px solid var(--line-2);border-radius:8px;padding:10px">'
    '<p class="sub" style="margin:0 0 8px">surface-2 + line-2: controls</p>'
    '<div style="background:var(--surface-3);border-radius:6px;padding:8px">'
    '<p class="sub" style="margin:0">surface-3: hover</p>'
    "</div></div></div></div>"
    '<p class="cap">Elevation is a surface step and a 1 px line, never a drop shadow.</p>'
  )
  radii = (
    '<div class="row" style="gap:16px">'
    + "".join(
      f'<div class="col" style="gap:4px"><div class="rbox" style="border-radius:{r.split()[0]}px"></div>'
      f'<span class="mono">{r} · {use}</span></div>'
      for r, use in RADII
    )
    + "</div>"
  )
  spacing = (
    '<table class="sheet">'
    + "".join(
      f'<tr><td class="mono">{n} px</td><td><div class="sbar" style="width:{n * 6}px"></div></td></tr>'
      for n in SPACING
    )
    + '</table><p class="cap">The even scale, plus 1 px for borders. Margins over 48 px are layout, not tokens.</p>'
  )
  glyphs = (
    '<div class="row" style="gap:14px;font-size:20px;color:var(--muted)">'
    + "".join(
      f'<span class="col" style="gap:4px;align-items:center">{icon(name)}'
      f'<span class="mono" style="font-size:10px">{name}</span></span>'
      for name in (
        "arrow-left",
        "arrow-up",
        "arrow-down",
        "chevron-right",
        "check",
        "x",
        "triangle-alert",
        "minus",
        "circle-small",
        "loader-circle",
        "git-branch",
        "settings",
      )
    )
    + '</div><p class="cap">Lucide glyphs inlined in index.html, drawn at 1 em in the text colour.</p>'
  )
  body = (
    '<div class="row">'
    + frame("Typography", "One ramp per width class, held in --fs-* tokens.", ramp)
    + frame("Colour", "Roles, not hues. One dark theme.", palette)
    + "</div>"
    + '<div class="row" style="margin-top:24px">'
    + frame("Surfaces", "Three steps up from the page.", surfaces)
    + frame("Corner radius", "Larger containers, larger radius.", radii)
    + frame("Spacing", "Padding, margin, and gap values.", spacing)
    + "</div>"
    + '<div class="row" style="margin-top:24px">'
    + frame("Icons", "The thirteen glyphs the page ships.", glyphs)
    + "</div>"
  )
  return board(
    "Style guide",
    "The tokens in the :root block of index.html, with the rule for each family.",
    body,
  )


def do_dont_board(_: dict[str, bytes]) -> str:
  def pair(
    title: str,
    do_text: str,
    do_html: str,
    dont_text: str,
    dont_html: str,
    width: int = 460,
  ) -> str:
    return (
      f'<div class="col" style="width:{width}px"><p class="lbl">{title}</p><div class="pair" style="width:100%">'
      f'<div class="frame"><div class="verdict do">{icon("check")} Do</div>{do_html}<p class="cap">{do_text}</p></div>'
      f'<div class="frame"><div class="verdict dont">{icon("x")} Do not</div>{dont_html}'
      f'<p class="cap">{dont_text}</p></div>'
      "</div></div>"
    )

  def meta_pills(gaps: tuple[int, int, int]) -> str:
    ahead = f"{icon('arrow-up')}23"
    return "".join(
      f'<span class="pill {cls}" style="margin-right:{g}px">{t}</span>'
      for g, cls, t in zip(gaps, ("mono", "", "mono ahead"), ("main", "#203", ahead))
    )

  spacing_do = f'<div class="off" style="gap:0">{meta_pills((6, 6, 0))}</div>'
  spacing_dont = f'<div class="off" style="gap:0">{meta_pills((5, 9, 0))}</div>'
  type_do = (
    '<p style="margin:0;font-size:var(--fs-3);font-weight:600">shop-web</p>'
    f'<p style="margin:6px 0 0">{pill("mono", "6f5a842", dot=False)}</p>'
  )
  type_dont = (
    '<p style="margin:0;font-size:13.5px;font-weight:600">shop-web</p>'
    '<p style="margin:6px 0 0"><span class="pill mono" style="font-size:11.5px">6f5a842</span></p>'
  )
  icon_do = f'<button class="btn ghost back">{icon("arrow-left")}All repos</button>'
  icon_dont = '<button class="btn ghost back"><span class="glyph">&lt;</span>&nbsp;All repos</button>'
  stack_do = (
    '<div class="narrow" style="display:grid;gap:8px"><input class="field" value="Demo User">'
    '<input class="field" value="demo@example.com"></div>'
  )
  stack_dont = (
    '<div class="narrow" style="display:flex;gap:8px"><input class="field" value="Demo User" style="width:50%">'
    '<input class="field" value="demo@example.com" style="width:50%"></div>'
  )
  banner_do = banner(
    "warn",
    "<b>This key is not assigned to your GitHub account.</b> Add it at github.com/settings/gpg/new.",
  )
  banner_dont = banner(
    "warn",
    "Warning: the system has detected that the currently active signing key may not have "
    "been associated with the authenticated GitHub account, which means that commits could appear "
    "as unverified until the situation is resolved by the user.",
  )
  honest_do = pill("warn", "checks unavailable", dot=False)
  honest_dont = pill("mono", "no PR", dot=False)
  body = (
    '<div class="row">'
    + pair(
      "Spacing",
      "Gaps from the even scale: 6 px between chips.",
      spacing_do,
      "5 and 9 px gaps: values nobody chose.",
      spacing_dont,
    )
    + pair(
      "Type",
      "Sizes from the ramp: 14 px name, 12 px mono hash.",
      type_do,
      "13.5 and 11.5 px: a ninth and tenth size.",
      type_dont,
    )
    + pair(
      "Icons",
      "The Lucide glyph at 1 em, stroked in the text colour.",
      icon_do,
      "A text glyph: wrong weight, wrong baseline, font dependent.",
      icon_dont,
    )
    + '</div><div class="row" style="margin-top:24px">'
    + pair(
      "Phone width",
      "Name and e-mail stack at 360 px; each field keeps 16 px text.",
      stack_do,
      "Side by side: the e-mail truncates and iOS zooms the field.",
      stack_dont,
      width=760,
    )
    + pair(
      "Honest pills",
      "Signed out, say what the app cannot know.",
      honest_do,
      "Claim no PR when gh never answered.",
      honest_dont,
    )
    + '</div><div class="row" style="margin-top:24px">'
    + pair(
      "Banners",
      "A bold lead, one action, a link to the fix.",
      banner_do,
      "A paragraph that explains before it asks.",
      banner_dont,
      width=900,
    )
    + "</div>"
  )
  return board(
    "Do and do not",
    "Pairs from the audit findings and the accepted decisions. The left side is the "
    "stylesheet as it is; the right side is what was there before, or what to avoid.",
    body,
  )


BOARDS: dict[str, Callable[[dict[str, bytes]], str]] = {
  "flow": flow_board,
  "wireframe-repo": wireframe_board,
  "views": views_board,
  "states": states_board,
  "components": components_board,
  "style": style_board,
  "do-dont": do_dont_board,
}


# -- rendering ----------------------------------------------------------------


def capture_views(walker: Walker, demo: Demo) -> dict[str, bytes]:
  shots: dict[str, bytes] = {}
  walker.goto(1500)
  shots["dashboard"] = walker.page.screenshot()
  demo.sign_in(False)
  demo.wait_until_checked(False)
  walker.goto(2500)
  shots["signed-out"] = walker.page.screenshot()
  demo.sign_in(True)
  demo.wait_until_checked(True)
  walker.goto(2000)
  walker.click(".repo-card", 800)
  walker.click('input[data-opt="dry_run"]', 0)
  walker.click("#start", 0)
  walker.wait_status("exit")
  walker.open_log()
  walker.page.wait_for_timeout(400)
  shots["after-run"] = walker.page.screenshot(full_page=True)
  walker.click("#settings-btn", 1500)
  shots["settings"] = walker.page.screenshot(full_page=True)
  return shots


def render(page: Any, base: str, css: str, icons: str, html: str, path: Path) -> None:
  page.set_content(
    HEAD.format(
      base=base, css=css, board=BOARD_CSS, body=html, icons=icons, fill=FILL_SLOTS
    )
  )
  page.evaluate("document.fonts.ready")
  page.wait_for_timeout(300)
  page.locator(".board").screenshot(path=str(path))


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
  parser.add_argument(
    "--out", type=Path, default=OUT, help="board directory (default docs/design)"
  )
  parser.add_argument(
    "--chromium",
    default=os.environ.get("WALK_CHROMIUM"),
    help="a Chromium binary to use instead of the one `playwright install` fetched",
  )
  args = parser.parse_args()
  from playwright.sync_api import sync_playwright

  args.out.mkdir(parents=True, exist_ok=True)
  css = app_css()
  icons = icon_script()
  with tempfile.TemporaryDirectory(prefix="boards-demo-") as tmp:
    demo = Demo(Path(tmp) / "demo")
    try:
      with sync_playwright() as playwright:
        browser = launch_browser(playwright, args.chromium)
        context = browser.new_context(**DESKTOP)
        walker = Walker(context, demo.url)
        shots = capture_views(walker, demo)
        context.close()
        if walker.errors:
          print("console errors while capturing:", *walker.errors, sep="\n  ")
          return 1
        context = browser.new_context(viewport={"width": BOARD_WIDTH, "height": 900})
        page = context.new_page()
        # The boards keep the demo origin, so the bundled fonts load without CORS.
        page.goto(demo.url + "/fonts/LICENSE.txt")
        for name, build in BOARDS.items():
          render(page, demo.url, css, icons, build(shots), args.out / f"{name}.png")
          print(f"wrote {args.out / f'{name}.png'}")
        context.close()
        browser.close()
    finally:
      demo.stop()
  return 0


if __name__ == "__main__":
  sys.exit(main())
