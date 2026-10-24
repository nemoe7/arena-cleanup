"""The web UI: repo store, one-click jobs, signing, auth, health, and the page shell."""

from __future__ import annotations

import json
import re
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from scripts import app_icon

from .conftest import ME_EMAIL, ROLLUPS, ROOT, World, engine_version, project_version

SERVER = ROOT / "ui" / "server.py"
STARTUP_SECONDS = 15
JOB_SECONDS = 20
MIN_FONT_BYTES = 20_000
# the nuu trio in em, so layouts follow the reader's browser font size
BREAKPOINTS = ("75em", "56.25em", "40em")
MINUTE = 60.0
TICK_SECONDS = 1.0
MIN_LOG_LINES = 5
MIN_ICONS = 3
PNG_MAGIC = b"\x89PNG"
CLONE_URL = "https://github.com/acme/shop-web.git"
GITHUB_FORMS = (
  "https://github.com/acme/shop-web",
  "https://github.com/acme/shop-web/",
  "https://github.com/acme/shop-web.git",
  "https://github.com/acme/shop-web/tree/main/docs",
  "https://www.github.com/acme/shop-web?tab=readme",
  "github.com/acme/shop-web",
  "  github.com/acme/shop-web\n",
)
OTHER_SOURCES = (
  "git@github.com:acme/shop-web.git",
  "https://gitlab.com/acme/shop-web",
  "/srv/repos/shop-web",
  "file:///tmp/bare.git",
)
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
CONTENT_JSON = {"Content-Type": "application/json"}
CREATED_OR_OK = {200, 201}
needs_gpg = pytest.mark.skipif(
  shutil.which("gpg") is None, reason="no gpg on this machine"
)


def free_port() -> int:
  with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    return sock.getsockname()[1]


class UI:
  """One UI server process on a free port, plus a tiny HTTP client."""

  def __init__(self, world: World) -> None:
    self.world = world
    self.data = world.root / "uidata"
    self.log = world.root / "ui.log"
    self.port = free_port()
    self.base = f"http://127.0.0.1:{self.port}"
    self.proc: subprocess.Popen[bytes] | None = None

  def start(self) -> None:
    with self.log.open("ab") as log:
      self.proc = subprocess.Popen(
        [
          sys.executable,
          str(SERVER),
          "--data",
          str(self.data),
          "--host",
          "127.0.0.1",
          "--port",
          str(self.port),
        ],
        # a fixed zone, so the log stamps are checkable below
        env={**self.world.env, "TZ": "Asia/Manila"},
        stdout=log,
        stderr=subprocess.STDOUT,
      )
    deadline = time.monotonic() + STARTUP_SECONDS
    while time.monotonic() < deadline:
      try:
        self.get("/api/env")
        return
      except (urllib.error.URLError, ConnectionError):
        time.sleep(0.25)
    raise RuntimeError(f"the UI did not start: {self.log.read_text()[-2000:]}")

  def stop(self) -> None:
    if self.proc is None:
      return
    self.proc.terminate()
    self.proc.wait(timeout=STARTUP_SECONDS)
    self.proc = None

  def request(
    self,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    timeout: float = 30,
  ) -> tuple[int, dict[str, str], bytes]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
      self.base + path, data=data, method=method, headers=CONTENT_JSON if body else {}
    )
    try:
      with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as err:
      return err.code, {k.lower(): v for k, v in err.headers.items()}, err.read()

  def status(self, method: str, path: str, body: dict[str, Any] | None = None) -> int:
    return self.request(method, path, body)[0]

  def get(self, path: str) -> Any:
    code, _, raw = self.request("GET", path)
    assert code == 200, (code, raw[:200])
    return json.loads(raw)

  def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
    code, _, raw = self.request("POST", path, body or {})
    assert code in CREATED_OR_OK, (code, raw[:200])
    return json.loads(raw)

  def text(self, path: str) -> str:
    code, _, raw = self.request("GET", path)
    assert code == 200, code
    return raw.decode()

  def wait_for_job(self, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + JOB_SECONDS
    snap = self.get(f"/api/jobs/{job_id}")
    while snap["status"] != "done" and time.monotonic() < deadline:
      time.sleep(0.25)
      snap = self.get(f"/api/jobs/{job_id}")
    return snap

  def event_stream(self, path: str, seconds: float = 3) -> str:
    """Read whatever an SSE endpoint sends within `seconds`."""
    req = urllib.request.Request(self.base + path)
    chunks = []
    try:
      with urllib.request.urlopen(req, timeout=seconds) as resp:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
          chunk = resp.read1(4096)
          if not chunk:
            break
          chunks.append(chunk)
    except (TimeoutError, urllib.error.URLError):
      pass
    return b"".join(chunks).decode(errors="replace")


AVATAR_PX = 40  # the server asks GitHub for this size
PNG = bytes.fromhex(
  "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
  "0000000d49444154789c636000020000050001e2b1ac770000000049454e44ae426082"
)


class Pictures:
  """A stand-in for GitHub's avatar host: one PNG for every path, hits counted."""

  def __init__(self) -> None:
    self.hits: list[str] = []
    hits = self.hits

    class Picture(BaseHTTPRequestHandler):
      def do_GET(self) -> None:
        hits.append(self.path)
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(PNG)))
        self.end_headers()
        self.wfile.write(PNG)

      def log_message(self, fmt: str, *args: object) -> None:
        pass

    self.server = ThreadingHTTPServer(("127.0.0.1", 0), Picture)
    self.url = f"http://127.0.0.1:{self.server.server_port}"
    threading.Thread(target=self.server.serve_forever, daemon=True).start()

  def stop(self) -> None:
    self.server.shutdown()


@pytest.fixture(scope="module")
def pictures() -> Pictures:
  host = Pictures()
  yield host
  host.stop()


@pytest.fixture(scope="module")
def ui(world: World, pictures: Pictures) -> UI:
  world.env["ARENA_AVATAR_HOST"] = pictures.url
  world.git("checkout", "-q", "main")
  world.only_arena()
  world.git("reset", "-q", "--hard", "origin/main")
  world.git("fetch", "-q", "--prune", "origin")
  if int(world.git("rev-list", "--count", "main")) < 2:
    # the commit list tests need a branch with more than one commit
    world.git(
      "commit",
      "-q",
      "--allow-empty",
      "-m",
      "chore: second commit for the commit list",
      "--no-gpg-sign",
    )
    world.git("push", "-q", "origin", "main")
  world.gh_state("open")
  world.gh_auth(True)
  server = UI(world)
  server.start()
  yield server
  server.stop()


@pytest.fixture(scope="module")
def ids() -> dict[str, str]:
  """Repo and job ids the tests create and later tests reuse."""
  return {}


def test_env_and_page(ui: UI) -> None:
  env = ui.get("/api/env")
  assert env["version"] == project_version()
  assert env["tool"] == engine_version()
  assert env["tools"]["git"] is True
  assert env["tools"]["gh"] is True
  assert env["data"] == str(ui.data)
  assert ui.get("/api/repos") == []

  page = ui.text("/")
  assert "<title>arena-cleanup</title>" in page
  assert not re.search(r'(src|href)="https?://', page), "page loads remote assets"
  assert 'color-scheme" content="dark"' in page
  assert not re.search(r"<link[^>]*stylesheet", page), (
    "page needs an external stylesheet"
  )
  for name in ("inter", "monaspace-neon"):
    path = f"fonts/{name}.woff2"
    assert f'<link rel="preload" href="{path}" as="font"' in page
    assert page.index(f'href="{path}"') < page.index("<style>")
    code, headers, font = ui.request("GET", "/" + path)
    assert code == 200
    assert headers["content-type"] == "font/woff2"
    assert len(font) > MIN_FONT_BYTES
  widths = re.findall(r"@media \(max-width: ([^)]+)\)", page)
  assert set(widths) == set(BREAKPOINTS), "three named widths, em only"
  assert len(widths) == 4, "1200 twice: the phone-first block and the rest"
  assert not re.search(r"@media \([^)]*width: \d+px", page)
  for gone in ("999px", "--pad: 14px", "font-size: 19px"):
    assert gone not in page, f"{gone} sits off the 4 px scale"
  assert "font-display: swap" not in page
  assert "Fallback" in page
  assert 'id="view-settings"' in page
  assert 'id="view-dashboard"' in page


def test_add_by_path(ui: UI, world: World, ids: dict[str, str]) -> None:
  added = ui.post("/api/repos", {"source": str(world.work)})
  ids["repo"] = added["id"]
  assert added["id"]
  code, _headers, body = ui.request("GET", f"/api/repos/{added['id']}/jobs/latest")
  assert (code, body) == (204, b""), "no run yet is not an error"
  assert ui.post("/api/repos", {"source": str(world.work)})["id"] == added["id"]
  assert len(ui.get("/api/repos")) == 1
  assert added["status"]["ok"] is True, added
  assert added["status"]["default"] == "main"
  status = added["status"]
  assert set(status["ahead"]) == set(status["arena"]), "one count per arena branch"
  assert set(status["activity"]) == set(status["arena"]), "one tip time per branch"
  assert all(stamp > 0 for stamp in status["activity"].values())
  assert added["managed"] is False
  assert len(json.loads((ui.data / "repos.json").read_text())) == 1


def test_github_page_addresses_normalize_to_clone_urls() -> None:
  sys.path.insert(0, str(ROOT))
  from ui.server import URL_RE, normalize_source

  for pasted in GITHUB_FORMS:
    assert normalize_source(pasted) == CLONE_URL, pasted
    assert URL_RE.match(normalize_source(pasted)), pasted
  for source in OTHER_SOURCES:
    assert normalize_source(source) == source


def test_add_by_clone_url(ui: UI, world: World, ids: dict[str, str]) -> None:
  bare = world.root / "work.git"
  world.git("clone", "-q", "--bare", str(world.work), str(bare), cwd=world.root)
  # three arena branches: level with main, a commit ahead, and one main moved past

  def git_bare(*args: str) -> str:
    return world.git(f"--git-dir={bare}", *args, cwd=world.root)

  git_bare("update-ref", "refs/heads/arena/ui-test", "refs/heads/main")
  tree = git_bare("rev-parse", "main^{tree}")
  ahead_tip = git_bare("commit-tree", tree, "-p", "main", "-m", "one more")
  git_bare("update-ref", "refs/heads/arena/ui-ahead", ahead_tip)
  git_bare("update-ref", "refs/heads/arena/ui-behind", "refs/heads/main^")
  clone = ui.post("/api/repos", {"source": f"file://{bare}"})
  ids["clone"] = clone["id"]
  ids["clone_path"] = clone["path"]
  assert clone["managed"] is True
  assert (Path(clone["path"]) / ".git").is_dir()
  assert clone["status"]["default"] == "main"
  assert any(b.startswith("arena/") for b in clone["status"]["arena"])
  assert clone["status"]["ahead"]["arena/ui-test"] == 0
  assert clone["status"]["ahead"]["arena/ui-ahead"] == 1, "commits beyond main"
  assert clone["status"]["ahead"]["arena/ui-behind"] == -1, "main moved past it"
  assert len(ui.get("/api/repos")) == 2
  assert ui.status("POST", "/api/repos", {"source": "/nope/nope"}) == 400
  assert ui.status("POST", "/api/repos", {"source": "  "}) == 400
  assert ui.status("GET", "/api/repos/deadbeef1234") == 404


def test_the_commit_list_follows_the_selected_arena_branch(
  ui: UI, ids: dict[str, str]
) -> None:
  clone = ids["clone"]
  on_main = ui.get(f"/api/repos/{clone}/commits?limit=2")
  ahead = ui.get(f"/api/repos/{clone}/commits?limit=2&ref=arena/ui-ahead")
  assert ahead["branch"] == "arena/ui-ahead"
  assert ahead["commits"][0]["subject"] == "one more", "the commit beyond main leads"
  assert ahead["commits"][1]["sha"] == on_main["commits"][0]["sha"], (
    "then main's history"
  )
  assert ahead["total"] == on_main["total"] + 1
  assert ui.status("GET", f"/api/repos/{clone}/commits?ref=arena/nope") == 404
  assert ui.status("GET", f"/api/repos/{clone}/commits?ref=-x") == 404
  assert ui.status("GET", f"/api/repos/{clone}/commits?ref=a..b") == 404


def test_delete_an_arena_branch_on_origin(
  ui: UI, world: World, ids: dict[str, str]
) -> None:
  clone = ids["clone"]
  bare = world.root / "work.git"
  gone = "arena/ui-behind"
  assert gone in ui.get(f"/api/repos/{clone}")["status"]["arena"]
  for name in ("main", "arena/nope", ""):
    assert (
      ui.status("POST", f"/api/repos/{clone}/arena/delete", {"branch": name}) == 400
    )
  answer = ui.post(f"/api/repos/{clone}/arena/delete", {"branch": gone})
  assert answer["deleted"] == gone
  assert gone not in answer["status"]["arena"]
  assert "arena/ui-test" in answer["status"]["arena"], "the other branches stay"
  refs = world.git(
    f"--git-dir={bare}", "for-each-ref", "--format=%(refname)", cwd=world.root
  )
  assert f"refs/heads/{gone}" not in refs
  assert "refs/heads/arena/ui-test" in refs
  assert ui.status("POST", f"/api/repos/{clone}/arena/delete", {"branch": gone}) == 400
  assert (
    ui.status("POST", "/api/repos/deadbeef1234/arena/delete", {"branch": gone}) == 404
  )
  page = ui.text("/")
  assert (
    'id="confirm-delete"' in page
    and 'class="btn danger" type="submit" value="delete"' in page
  )


def test_a_fetch_on_demand_sees_a_new_remote_branch(
  ui: UI, world: World, ids: dict[str, str]
) -> None:
  bare = world.root / "work.git"
  world.git(f"--git-dir={bare}", "update-ref", "refs/heads/arena/ui-late", "main")
  before = ui.get(f"/api/repos/{ids['clone']}")["status"]["arena"]
  assert "arena/ui-late" not in before, "nothing fetched yet"
  after = ui.post("/api/fetch", {"force": True})
  clone = next(r for r in after if r["id"] == ids["clone"])
  assert "arena/ui-late" in clone["status"]["arena"]
  assert "arena/ui-late" in ui.get(f"/api/repos/{ids['clone']}")["status"]["arena"]
  # a second branch right after: the server skips its unforced fetch, not the
  # Reload one
  world.git(f"--git-dir={bare}", "update-ref", "refs/heads/arena/ui-later", "main")
  skipped = ui.post("/api/fetch", {})
  clone = next(r for r in skipped if r["id"] == ids["clone"])
  assert "arena/ui-later" not in clone["status"]["arena"], "debounced"
  forced = ui.post("/api/fetch", {"force": True})
  clone = next(r for r in forced if r["id"] == ids["clone"])
  assert "arena/ui-later" in clone["status"]["arena"]


def test_the_fetch_counter_reports_two_steps_per_repo(ui: UI) -> None:
  repos = ui.get("/api/repos")
  ui.post("/api/fetch", {"force": True})
  progress = ui.get("/api/progress")
  assert progress["active"] is False, "the fetch finished before the reply"
  assert progress["total"] == 2 * len(repos), "one fetch and one status per repo"
  assert progress["done"] == progress["total"]


def test_the_fetch_counter_climbs_while_the_fetch_runs(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  sys.path.insert(0, str(ROOT))
  from ui import server

  seen: list[dict[str, Any]] = []

  def fetch(repo: dict[str, Any]) -> bool:
    seen.append(server.PROGRESS.read())
    return True

  def status(repo: dict[str, Any]) -> dict[str, Any]:
    seen.append(server.PROGRESS.read())
    return {"ok": True}

  monkeypatch.setattr(server, "fetch_origin", fetch)
  monkeypatch.setattr(server, "repo_status", status)
  repos = [{"id": f"r{n}", "path": f"/nowhere/{n}", "name": f"r{n}"} for n in range(3)]
  server.fetch_all(repos)
  assert [p["active"] for p in seen] == [True] * 6, "live during both phases"
  assert all(p["total"] == 6 for p in seen)
  assert max(p["done"] for p in seen) >= 3, "the status phase sees the fetches done"
  assert server.PROGRESS.read() == {"active": False, "done": 6, "total": 6}


def test_the_pill_carries_each_check_with_its_run_link(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  sys.path.insert(0, str(ROOT))
  from ui import server

  rollup = [
    {**ROLLUPS["superseded-failing"][0], "detailsUrl": "https://ci/build/1"},
    {**ROLLUPS["superseded-failing"][1], "detailsUrl": "https://ci/build/2"},
    {**ROLLUPS["superseded-failing"][2], "detailsUrl": "https://ci/test/1"},
    {"name": "deploy", "status": "IN_PROGRESS", "conclusion": ""},
  ]

  def fake_gh(argv: list[str], **_: Any) -> tuple[int, str, str]:
    pr = {"number": 7, "title": "t", "url": "u", "statusCheckRollup": rollup}
    return 0, json.dumps([pr]), ""

  monkeypatch.setattr(server, "run_cmd", fake_gh)
  monkeypatch.setattr(server.shutil, "which", lambda name: "/usr/bin/gh")
  pr = server.pr_checks("arena/x", str(ROOT))
  assert pr is not None
  assert [(c["name"], c["result"]) for c in pr["checks"]] == [
    ("build", "passed"),
    ("test", "failed"),
    ("deploy", "running"),
  ], "one row per name, the pass wins over the cancelled attempt"
  assert [c["url"] for c in pr["checks"]] == [
    "https://ci/build/1",
    "https://ci/test/1",
    "",
  ]
  assert pr["total"] == len(pr["checks"])


def test_one_fetch_runs_at_a_time_and_the_rest_wait_for_it(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  sys.path.insert(0, str(ROOT))
  from ui import server

  calls: list[float] = []

  def slow_fetch(repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls.append(time.monotonic())
    time.sleep(0.5)
    return repos

  monkeypatch.setattr(server, "fetch_all", slow_fetch)
  gate = server.FetchGate(debounce=1.0)
  assert gate.run([]) is True, "the first call fetches"
  assert gate.run([]) is False, "within the debounce: skipped"
  assert gate.run([], force=True) is True, "Reload skips the debounce"
  results: list[bool] = []
  threads = [
    threading.Thread(target=lambda: results.append(gate.run([], force=True)))
    for _ in range(6)
  ]
  for thread in threads:
    thread.start()
  for thread in threads:
    thread.join()
  assert results.count(True) == 1, "six Reload clicks at once: one fetch"
  assert len(calls) == 3
  time.sleep(1.0)
  assert gate.run([]) is True, "after the debounce the tick fetches again"


def test_the_pill_counts_checks_by_the_engine_rule(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  """A superseded CANCELLED attempt next to the new SUCCESS of the same name
  does not make the pill red. The engine already reads the rollup that way."""
  sys.path.insert(0, str(ROOT))
  from ui import server

  rollups = iter([ROLLUPS["superseded"], ROLLUPS["superseded-failing"]])

  def fake_gh(argv: list[str], **_: Any) -> tuple[int, str, str]:
    assert argv[:3] == ["gh", "pr", "list"]
    pr = {"number": 7, "title": "t", "url": "u", "statusCheckRollup": next(rollups)}
    return 0, json.dumps([pr]), ""

  monkeypatch.setattr(server, "run_cmd", fake_gh)
  monkeypatch.setattr(server.shutil, "which", lambda name: "/usr/bin/gh")
  green = server.pr_checks("arena/x", str(ROOT))
  assert green is not None
  assert (green["total"], green["passed"], green["failed"]) == (2, 2, 0)
  assert green["state"] == "passing"
  red = server.pr_checks("arena/x", str(ROOT))
  assert red is not None
  assert (red["total"], red["passed"], red["failed"]) == (2, 1, 1)
  assert red["state"] == "failing"


def test_the_running_pill_is_amber_like_github(ui: UI) -> None:
  """GitHub paints a pending check amber. The running pill and the sidebar
  dot share the warn colour, and no blue pill variant remains."""
  page = ui.text("/")
  assert 'pr.state === "running" ? "warn" : "mono"' in page
  assert 'pr.state === "failing" ? "var(--err)" : "var(--warn)"' in page
  assert 'if (!pr || pr.state === "none") return "var(--line-2)";' in page
  assert ".pill.run" not in page


def test_no_surface_casts_a_drop_shadow(ui: UI) -> None:
  """nuu rule 6: no shadow. A box-shadow is a focus ring, an inset bar, or none."""
  page = ui.text("/")
  shadows = re.findall(r"box-shadow: ([^;]+);", page)
  assert len(shadows) >= 3, "the focus rings are still there"
  for value in shadows:
    assert value.startswith(("0 0 0 3px", "inset", "none")), value


def test_every_transition_shares_one_curve_and_one_band(ui: UI) -> None:
  """nuu rule 8: one curve over 160 to 220 ms, so each transition names the tokens."""
  page = ui.text("/")
  assert "--ease: cubic-bezier(.22, 1, .36, 1);" in page
  assert re.search(r"--fast: (16\d|1[7-9]\d|2[01]\d|220)ms;", page)
  transitions = re.findall(r"transition: ([^;]+);", page)
  assert len(transitions) >= 5
  for value in transitions:
    for part in value.split(","):
      assert part.strip().endswith("var(--fast) var(--ease)"), value


def test_hover_rules_wait_for_a_pointer(ui: UI) -> None:
  """nuu rule 9: hover only under the media query, and focus and active everywhere."""
  page = ui.text("/")
  hovers = [line.strip() for line in page.splitlines() if ":hover" in line]
  assert len(hovers) >= 15
  assert [
    line for line in hovers if not line.startswith("@media (hover: hover) {")
  ] == []
  plain = [line for line in page.splitlines() if ":hover" not in line]
  assert any(":focus-visible" in line for line in plain)
  assert any(":active" in line for line in plain)


def test_colours_live_in_root_tokens_only(ui: UI) -> None:
  """nuu rule 3: every colour is a role token, so no rule below :root names one."""
  page = ui.text("/")
  style = page[page.index("<style>") : page.index("</style>")]
  start = style.index(":root {")
  end = style.index("\n  }\n", start)
  root, rules = style[start:end], style[:start] + style[end:]
  literal = re.compile(r"#[0-9a-fA-F]{3,8}(?![\w-])|rgba?\(")
  assert len(literal.findall(root)) >= 40
  assert literal.findall(rules) == []


def test_the_fetch_clock_is_aligned_and_ticks(
  ui: UI, world: World, ids: dict[str, str]
) -> None:
  sys.path.insert(0, str(ROOT))
  from ui.server import FETCH_PERIOD, Fetcher, Registry, seconds_to_next_tick

  assert FETCH_PERIOD == MINUTE
  assert seconds_to_next_tick(120.0) == MINUTE, "on the mark, wait a whole period"
  assert seconds_to_next_tick(125.5) == MINUTE - 5.5
  assert 0 < seconds_to_next_tick(time.time()) <= MINUTE

  bare = world.root / "work.git"
  world.git(f"--git-dir={bare}", "update-ref", "refs/heads/arena/ui-tick", "main")
  clone = Path(ids["clone_path"])
  fetcher = Fetcher(Registry(ui.data), period=TICK_SECONDS)
  fetcher.start()
  try:
    deadline = time.monotonic() + STARTUP_SECONDS
    while time.monotonic() < deadline:
      refs = world.git("branch", "-r", cwd=clone)
      if "origin/arena/ui-tick" in refs:
        break
      time.sleep(0.1)
    assert "origin/arena/ui-tick" in refs, "the tick fetched the clone"
  finally:
    fetcher.stop.set()
    fetcher.join(timeout=STARTUP_SECONDS)
  assert not fetcher.is_alive()


def test_a_second_add_of_the_same_url_reuses_the_clone(
  ui: UI, world: World, ids: dict[str, str]
) -> None:
  bare = world.root / "work.git"
  clones = Path(ids["clone_path"]).parent
  # the same repo again, spelled without `.git`: the same card, no second clone
  again = ui.post("/api/repos", {"source": f"file://{world.root / 'work'}"})
  assert again["id"] == ids["clone"]
  assert again["path"] == ids["clone_path"]
  assert len(ui.get("/api/repos")) == 2
  # a forgotten card leaves its directory behind: the next add reuses it
  ui.post(f"/api/repos/{ids['clone']}/remove", {"delete": False})
  assert Path(ids["clone_path"]).is_dir()
  back = ui.post("/api/repos", {"source": f"file://{bare}"})
  assert back["id"] == ids["clone"]
  assert back["path"] == ids["clone_path"]
  # another repo with the same name still gets its own directory
  other = world.root / "other" / "work.git"
  other.parent.mkdir(exist_ok=True)
  world.git("clone", "-q", "--bare", str(world.work), str(other), cwd=world.root)
  second = ui.post("/api/repos", {"source": f"file://{other}"})
  assert second["id"] != ids["clone"]
  assert Path(second["path"]) == clones / "work-2"
  ui.post(f"/api/repos/{second['id']}/remove", {"delete": True})
  assert not Path(second["path"]).exists()
  assert sorted(p.name for p in clones.iterdir()) == ["work"]
  assert len(ui.get("/api/repos")) == 2


def test_a_run_resets_a_managed_clone(
  ui: UI, world: World, ids: dict[str, str]
) -> None:
  path = Path(ids["clone_path"])

  def git(*args: str) -> str:
    return world.git("-c", "commit.gpgsign=false", *args, cwd=path)

  # local work: a stale arena copy with a commit, and a dirty tree
  git("checkout", "-q", "-b", "arena/stale-copy")
  (path / "junk.txt").write_text("stale\n")
  git("add", "junk.txt")
  git(
    "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "stale"
  )
  tracked = git("ls-files").splitlines()[0]
  (path / tracked).write_text("dirty\n")
  assert git("status", "--porcelain") != ""

  job = ui.post(
    f"/api/repos/{ids['clone']}/jobs",
    {"action": "run", "dry_run": True, "arena": "arena/ui-test"},
  )
  assert ui.wait_for_job(job["id"])["status"] == "done"
  assert git("rev-parse", "--abbrev-ref", "HEAD") == "main"
  assert git("rev-parse", "HEAD") == git("rev-parse", "origin/main")
  assert git("status", "--porcelain") == "", "origin wins over local changes"
  assert git("branch", "--list", "arena/*") == "", "local arena copies are gone"
  assert "arena/ui-test" in ui.get(f"/api/repos/{ids['clone']}")["status"]["arena"]


def test_one_click_dry_run_job(ui: UI, world: World, ids: dict[str, str]) -> None:
  before = world.rev()
  job = ui.post(
    f"/api/repos/{ids['repo']}/jobs",
    {"action": "clean", "dry_run": True, "branch": "main"},
  )
  ids["job"] = job["id"]
  assert "--dry-run" in job["argv"], job
  assert not any(a.startswith("--on-divergence") for a in job["argv"]), (
    "one click chose a divergence policy"
  )
  snap = ui.wait_for_job(job["id"])
  assert snap["status"] == "done"
  assert snap["exit"] == 0, snap
  assert len(snap["lines"]) > MIN_LOG_LINES
  assert "arena-cleanup" in snap["lines"][0]["text"]
  assert world.rev() == before
  assert "data: " in ui.event_stream(f"/api/jobs/{job['id']}/events")


def test_the_latest_run_of_a_repo_is_kept(ui: UI, ids: dict[str, str]) -> None:
  latest = ui.get(f"/api/repos/{ids['repo']}/jobs/latest")
  assert latest["id"] == ids["job"]
  assert latest["status"] == "done"
  assert len(latest["lines"]) > MIN_LOG_LINES, "the whole log, not a tail"
  saved = json.loads((ui.data / "jobs" / f"{ids['repo']}.json").read_text())
  assert saved["id"] == ids["job"]
  assert saved["lines"] == latest["lines"]
  assert ui.status("GET", "/api/repos/deadbeef1234/jobs/latest") == 404


def test_reset_to_origin(ui: UI, world: World, ids: dict[str, str]) -> None:
  world.git("checkout", "-q", "main")
  world.commit("someone", "someone@example.com", "2024-02-01T10:00:00+08:00", "wip")
  (world.work / "scratch.txt").write_text("untracked\n")
  assert world.rev() != world.rev("origin/main")

  out = ui.post(f"/api/repos/{ids['repo']}/reset", {})
  assert out["reset"] == "origin/main"
  assert out["status"]["branch"] == "main"
  assert world.rev() == world.rev("origin/main")
  assert (world.work / "scratch.txt").exists(), "a hard reset must keep untracked files"
  (world.work / "scratch.txt").unlink()
  assert ui.status("POST", "/api/repos/nope/reset", {}) == 404


def test_the_remote_row_shows_the_configured_url(
  ui: UI, world: World, ids: dict[str, str]
) -> None:
  page = "https://github.com/acme/work"
  world.git("remote", "set-url", "origin", page)
  world.git("config", f"url.{world.origin}.insteadOf", page)
  try:
    # reset answers with a fresh status, and its fetch rides the rewrite
    out = ui.post(f"/api/repos/{ids['repo']}/reset", {})
    assert out["reset"] == "origin/main"
    assert out["status"]["remote"] == page
  finally:
    world.git("config", "--unset", f"url.{world.origin}.insteadOf")
    world.git("remote", "set-url", "origin", str(world.origin))


def test_the_argv_whitelist(ui: UI, ids: dict[str, str]) -> None:
  jobs = f"/api/repos/{ids['repo']}/jobs"
  assert ui.status("POST", jobs, {"action": "rm -rf /"}) == 400
  assert ui.status("POST", jobs, {"action": "run", "nope": 1}) == 400
  assert ui.status("POST", jobs, {"action": "run", "keep_empty": True}) == 400
  assert ui.status("POST", jobs, {"action": "run", "branch": "--upload-pack=x"}) == 400
  assert ui.status("POST", jobs, {"action": "run", "paths": ["-x"]}) == 400
  assert ui.status("POST", jobs, {"action": "strip"}) == 400, "strip is CLI only"
  arena = {"action": "run", "branch": "arena/session-1", "dry_run": True}
  assert ui.status("POST", jobs, arena) == 400, "the page never targets arena/*"
  assert ui.status("POST", jobs, {"action": "run", "arena": "main"}) == 400
  chosen = ui.post(jobs, {"action": "run", "arena": "arena/session-1", "dry_run": True})
  assert chosen["argv"][-2:] == ["--arena", "arena/session-1"], chosen["argv"]
  ui.wait_for_job(chosen["id"])  # let the dry run end before the next test
  assert ui.status("POST", jobs, {"action": "run", "timeout": -5}) == 400
  assert ui.status("POST", "/api/repos/deadbeef1234/jobs", {"action": "run"}) == 404
  assert ui.status("POST", "/api/jobs/deadbeef1234/cancel") == 404


def test_signing_panel(ui: UI) -> None:
  sign = ui.get("/api/signing")
  assert isinstance(sign["keys"], list)
  assert isinstance(sign["github"], dict)
  assert "error" in sign["github"] and "checked" in sign["github"]
  assert (sign["format"] or "openpgp") == "openpgp"
  assert ui.status("POST", "/api/signing", {"action": "nope"}) == 400
  assert ui.status("POST", "/api/signing", {"action": "use"}) == 400


def test_settings_page(ui: UI, world: World) -> None:
  before = ui.get("/api/settings")
  assert before["identity"] == {"name": "nemoe7", "email": ME_EMAIL}
  assert before["claims"]["emails"] == [] and before["claims"]["names"] == []
  assert ME_EMAIL in before["claims"]["defaults"]["emails"]
  assert "arena" in before["claims"]["defaults"]["names"]

  saved = ui.post(
    "/api/settings",
    {
      "action": "claims",
      "emails": [" a@x.io ", "a@x.io", ""],
      "names": ["bot one", "arena"],
    },
  )
  assert saved["claims"]["emails"] == ["a@x.io"]
  assert saved["claims"]["names"] == ["bot one", "arena"]
  assert world.git(
    "config", "--global", "--get-all", "arena.claim-name"
  ).splitlines() == [
    "bot one",
    "arena",
  ]
  cleared = ui.post("/api/settings", {"action": "claims", "emails": [], "names": []})
  assert cleared["claims"] == {**saved["claims"], "emails": [], "names": []}

  renamed = ui.post(
    "/api/settings", {"action": "identity", "name": "Some One", "email": "some@one.io"}
  )
  assert renamed["identity"] == {"name": "Some One", "email": "some@one.io"}
  assert world.git("config", "--global", "user.email") == "some@one.io"
  ui.post("/api/settings", {"action": "identity", "name": "nemoe7", "email": ME_EMAIL})

  assert ui.status("POST", "/api/settings", {"action": "identity", "name": "x"}) == 400
  assert (
    ui.status(
      "POST", "/api/settings", {"action": "identity", "name": "x", "email": "no"}
    )
    == 400
  )
  assert (
    ui.status("POST", "/api/settings", {"action": "claims", "emails": "a@x.io"}) == 400
  )
  assert ui.status("POST", "/api/settings", {"action": "nope"}) == 400


@needs_gpg
def test_signing_panel_with_a_key(ui: UI) -> None:
  sign = ui.get("/api/signing")
  assert sign["gpg"] is True
  assert sign["keys"], "the throwaway key is not listed"
  fpr = sign["keys"][0]["fingerprint"]
  pub = ui.post("/api/signing", {"action": "public_key", "fingerprint": fpr})
  assert "BEGIN PGP PUBLIC KEY BLOCK" in pub["public_key"]
  assert ui.post("/api/signing", {"action": "use", "fingerprint": fpr})["active"] == fpr


def test_safety(ui: UI) -> None:
  assert ui.status("GET", "/../../etc/passwd") == 404
  assert ui.status("GET", "/api/nope") == 404


def test_authentication(ui: UI, world: World) -> None:
  auth = ui.get("/api/auth")
  assert isinstance(auth["gh"], dict)
  assert "authenticated" in auth["gh"] and "installed" in auth["gh"]
  assert "credential_helpers" in auth["git"] and "ssh_keys" in auth["git"]
  assert "GH_TOKEN" in auth["env"]
  assert (
    ui.status("POST", "/api/auth", {"action": "token", "token": "not a token"}) == 400
  )
  assert ui.status("POST", "/api/auth", {"action": "token", "token": ""}) == 400
  assert ui.status("POST", "/api/auth", {"action": "sudo"}) == 400
  assert "pr_checked" in ui.get("/api/repos")[0]["status"]

  # the test can sign the fake gh out. That state used to look like
  # "these branches have no PR".
  world.gh_auth(False)
  signed_out = ui.post("/api/auth", {"action": "check"})
  assert signed_out["gh"]["authenticated"] is False
  assert "not logged" in signed_out["gh"]["error"].lower()
  status = ui.get("/api/repos")[0]["status"]
  assert status["pr_checked"] is False
  assert "not signed in" in status["pr_reason"].lower()
  world.gh_auth(True)
  signed_in = ui.post("/api/auth", {"action": "check"})
  assert signed_in["gh"]["login"] == "nemoe7"
  assert "repo" in signed_in["gh"]["scopes"]


def test_health(ui: UI) -> None:
  # docker's HEALTHCHECK calls this on a 30s interval, so it has to be cheap
  code, _, raw = ui.request("GET", "/healthz")
  assert code == 200
  health = json.loads(raw)
  assert health["ok"] is True
  assert SEMVER.match(health["version"])
  assert health["version"] == project_version()
  assert isinstance(health["uptime"], float)
  assert health["repos"] == len(ui.get("/api/repos"))
  assert 'id="start"' in ui.text("/")


def test_a_cancelled_job_is_marked_cancelled() -> None:
  # Cancel must be distinguishable from a crash. Drive the Job object directly
  # so the test cannot race a real run.
  sys.path.insert(0, str(ROOT))
  from ui.server import Job

  job = Job(["sleep", "30"], "/tmp", {"id": "t", "name": "t"})
  job.start()
  time.sleep(0.3)
  assert job.cancel() is True
  deadline = time.monotonic() + STARTUP_SECONDS
  snap = job.snapshot()
  while snap["status"] != "done" and time.monotonic() < deadline:
    time.sleep(0.1)
    snap = job.snapshot()
  assert snap["status"] == "done"
  assert snap["cancelled"] is True
  assert snap["exit"] != 0


def test_a_finished_job_drops_the_status_cache(monkeypatch: pytest.MonkeyPatch) -> None:
  # a finished run changed this clone, so its status read asks git again
  sys.path.insert(0, str(ROOT))
  from ui import server

  repo = {"id": "fresh", "name": "fresh", "path": "/tmp"}
  reads: list[str] = []
  monkeypatch.setattr(
    server, "repo_status", lambda r: reads.append(r["id"]) or {"ok": True}
  )
  server.STATUS.get(repo)
  server.STATUS.get(repo)
  assert reads == ["fresh"], "the second read came from the cache"
  job = server.Job(["true"], "/tmp", repo)
  job.start()
  deadline = time.monotonic() + STARTUP_SECONDS
  while job.snapshot()["status"] != "done" and time.monotonic() < deadline:
    time.sleep(0.1)
  server.STATUS.get(repo)
  assert reads == ["fresh", "fresh"], "the run end dropped the cached status"
  server.STATUS.drop("fresh")


def test_pr_checks_are_read_once_a_minute_and_again_after_a_drop_or_fetch(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  # PR checks keep for the minute fetch, which reads them anew. A run end or
  # a sign-in change drops them sooner.
  sys.path.insert(0, str(ROOT))
  from ui import server

  assert server.PR_TTL >= server.FETCH_PERIOD, "the minute fetch is the one reader"
  repo = {"id": "minute", "name": "minute", "path": "/tmp"}
  reads: list[str] = []

  def read() -> dict[str, int]:
    reads.append("pr")
    return {"number": 1}

  assert server.STATUS.pr(repo, "arena/x", read) == {"number": 1}
  assert server.STATUS.pr(repo, "arena/x", read) == {"number": 1}
  assert reads == ["pr"], "the second read came from the cache"
  server.STATUS.drop("minute")
  server.STATUS.pr(repo, "arena/x", read)
  assert reads == ["pr", "pr"], "a drop reads the checks again"
  monkeypatch.setattr(server, "repo_status", lambda r: {"ok": True})
  server.STATUS.refresh([repo])
  server.STATUS.pr(repo, "arena/x", read)
  assert reads == ["pr", "pr", "pr"], "the fetch refresh reads the checks again"
  server.STATUS.drop("minute")


def test_a_live_job_marks_its_repo_as_running() -> None:
  # The dashboard reads this flag, so a slow job must show while it runs and
  # leave with the process.
  sys.path.insert(0, str(ROOT))
  from ui.server import JOBS, JOBS_LOCK, Job, running_repo_ids

  job = Job(["sleep", "30"], "/tmp", {"id": "live", "name": "live"})
  with JOBS_LOCK:
    JOBS[job.id] = job
  try:
    job.start()
    assert "live" in running_repo_ids()
    assert job.cancel() is True
    deadline = time.monotonic() + STARTUP_SECONDS
    while job.snapshot()["status"] != "done" and time.monotonic() < deadline:
      time.sleep(0.1)
    assert "live" not in running_repo_ids()
  finally:
    with JOBS_LOCK:
      JOBS.pop(job.id, None)


def test_the_brand_mark_and_the_app_icon_share_one_glyph(ui: UI) -> None:
  page = ui.text("/")
  assert 'class="brand" href="#/"' in page
  assert '<span class="ico-svg" data-icon="broom-sparkles" aria-hidden="true">' in page
  entry = re.search(
    r'"broom-sparkles": svg\(paths\((.*?)\) \+ \'<g class="sparkles">\' \+ paths\((.*?)\)'
    r' \+ "</g>"\),',
    page,
  )
  assert entry
  assert tuple(json.loads(f"[{entry.group(1)}]")) == app_icon.BROOM
  assert tuple(json.loads(f"[{entry.group(2)}]")) == app_icon.SPARKLES
  assert app_icon.GLYPH == app_icon.BROOM + app_icon.SPARKLES


def test_pwa_assets(ui: UI) -> None:
  manifest = ui.get("/manifest.webmanifest")
  assert manifest["display"] == "standalone"
  assert manifest["start_url"] == "/"
  assert len(manifest["icons"]) >= MIN_ICONS
  assert any(i.get("purpose") == "maskable" for i in manifest["icons"])
  assert (
    ui.request("GET", "/manifest.webmanifest")[1]["content-type"]
    == "application/manifest+json; charset=utf-8"
  )
  page = ui.text("/")
  assert page.count('rel="manifest"') == 1
  for icon, (side, _, _) in app_icon.PICTURES.items():
    code, _, raw = ui.request("GET", f"/icons/{icon}")
    assert code == 200 and raw[:4] == PNG_MAGIC, icon
    assert struct.unpack(">II", raw[16:24]) == (side, side), icon
  code, headers, raw = ui.request("GET", "/sw.js")
  assert headers["content-type"] == "application/javascript; charset=utf-8"
  assert "no-store" in headers["cache-control"]
  assert headers["service-worker-allowed"] == "/"
  worker = raw.decode()
  assert "arena-shell" in worker
  assert 'url.pathname.startsWith("/api/")' in worker, "the worker caches API responses"
  assert "apple-mobile-web-app-capable" in page
  assert "serviceWorker.register" in page


def test_the_icon_licences_ship_beside_the_page(ui: UI) -> None:
  for name, head in (("lucide", b"ISC License"), ("octicons", b"MIT License")):
    code, _, raw = ui.request("GET", f"/LICENSE-{name}.txt")
    assert code == 200, name
    assert raw.startswith(head), name


def test_repos_survive_a_restart_and_can_be_forgotten(
  ui: UI, ids: dict[str, str]
) -> None:
  newest = ui.get(f"/api/repos/{ids['repo']}/jobs/latest")["id"]
  ui.stop()
  ui.start()
  repos = ui.get("/api/repos")
  assert len(repos) == 2
  assert repos[0]["status"]["ok"] is True
  latest = ui.get(f"/api/repos/{ids['repo']}/jobs/latest")
  assert latest["id"] == newest, "the saved run outlives a restart"
  assert latest["status"] == "done"
  assert ui.get(f"/api/repos/{ids['clone']}/jobs/latest")["status"] == "done"
  removed = ui.post(f"/api/repos/{ids['clone']}/remove", {"delete": True})
  assert removed["removed"] == ids["clone"]
  assert len(ui.get("/api/repos")) == 1
  assert not Path(ids["clone_path"]).exists()
  assert not (ui.data / "jobs" / f"{ids['clone']}.json").exists()
  assert ui.status("GET", f"/api/repos/{ids['clone']}/jobs/latest") == 404


LOG_LINE = re.compile(
  r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \+0800 (INFO|WARNING|ERROR) "
)


def test_the_container_log_names_jobs_and_errors_in_the_tz_zone(
  ui: UI, ids: dict[str, str]
) -> None:
  lines = ui.log.read_text().splitlines()
  stamped = [line for line in lines if LOG_LINE.match(line)]
  assert stamped, lines[-5:]
  assert all(LOG_LINE.match(line) for line in lines if " arena-ui " in line)
  assert any(" arena-ui " in line and "tz=PST +0800" in line for line in stamped)
  assert any(f"job {ids['job']} start" in line for line in stamped)
  assert any(f"job {ids['job']} done" in line and "exit 0" in line for line in stamped)
  assert any("repo add work " in line for line in stamped)
  assert any("repo remove work and its clone" in line for line in stamped)
  assert any("GET /api/repos/deadbeef1234 -> 404" in line for line in stamped)


COMMIT_FIELDS = {"sha", "short", "subject", "author", "date", "signed", "avatar"}
SHORT_SHA = 7


def test_the_commit_list_and_the_page_shell(ui: UI, ids: dict[str, str]) -> None:
  repo = ids["repo"]
  commits = ui.get(f"/api/repos/{repo}/commits?limit=2")
  assert len(commits["commits"]) == 2
  assert commits["total"] >= 2
  assert all(COMMIT_FIELDS <= set(c) for c in commits["commits"])
  assert all(len(c["short"]) == SHORT_SHA for c in commits["commits"]), (
    "GitHub short SHA"
  )
  assert commits["branch"] != ""
  assert len(ui.get(f"/api/repos/{repo}/commits?limit=0")["commits"]) == 1
  assert ui.status("GET", f"/api/repos/{repo}/commits?limit=100000") == 200
  assert ui.status("GET", f"/api/repos/{repo}/commits?limit=abc") == 200
  assert ui.status("GET", "/api/repos/deadbeef1234/commits") == 404
  # paging: `next` names the last commit of a full page, `before` continues after it
  first = ui.get(f"/api/repos/{repo}/commits?limit=1")
  assert first["next"] == first["commits"][0]["sha"]
  second = ui.get(f"/api/repos/{repo}/commits?limit=1&before={first['next']}")
  assert [c["sha"] for c in second["commits"]] == [commits["commits"][1]["sha"]]
  assert second["total"] == first["total"]
  everything = ui.get(f"/api/repos/{repo}/commits?limit=100")
  assert everything["next"] is None, "the last page carries no cursor"
  tail = ui.get(
    f"/api/repos/{repo}/commits?limit=100&before={everything['commits'][-1]['sha']}"
  )
  assert tail["commits"] == [] and tail["next"] is None
  assert ui.status("GET", f"/api/repos/{repo}/commits?before=nope") == 400
  assert ui.get(f"/api/repos/{repo}/commits?before={'0' * 40}")["commits"] == []

  page = ui.text("/")
  assert 'id="commits"' in page
  assert 'id="logwrap"' in page
  assert 'id="logwrap" hidden' not in page, "the log starts open"
  assert 'id="logtoggle"' not in page
  assert 'id="phases"' in page
  assert 'class="brand" href="#/"' in page
  assert 'id="task-note"' not in page, "the task note went with the hint texts"
  assert 'id="timeout" type="range"' in page and 'id="timeout-out"' in page
  assert 'data-opt="update_tags" checked' in page
  assert 'data-opt="force">No lease</label>' in page
  assert 'data-opt="keep_branch"' not in page, "no local arena branch survives a run"
  assert 'data-opt="keep_empty"' not in page, "empty commits are always dropped"
  assert 'id="start-mobile"' in page
  assert not re.search(
    r'cmdpreview|id="cmdline"|id="emptystate"|oneclick-mobile|cmdswitch|data-cmd=', page
  ), "the removed command strip and switch"


TREE_FILES = {"docs/guide.md": "# guide\n", "notes.txt": "notes\n"}


def test_the_commit_pictures_come_once_per_address(
  ui: UI, world: World, ids: dict[str, str], pictures: Pictures
) -> None:
  repo = ids["repo"]
  commits = ui.get(f"/api/repos/{repo}/commits")["commits"]
  authors = world.git("log", f"-{len(commits)}", "--format=%ae%x1f%an", "HEAD")
  by_name = dict(line.split("\x1f")[::-1] for line in authors.splitlines())
  noreply = {m for m in by_name.values() if m.endswith("@users.noreply.github.com")}
  assert noreply and len(by_name) > len(noreply), "noreply and plain addresses on HEAD"
  for commit in commits:
    # the clone's origin is a local path, so only a noreply address has a picture
    assert bool(commit["avatar"]) == (by_name[commit["author"]] in noreply)
  keys = {c["avatar"] for c in commits if c["avatar"]}
  assert len(keys) == len(noreply)
  ui.get(f"/api/repos/{repo}/commits")
  # every commit list so far, this one and the earlier ones, cost one download
  assert pictures.hits == [f"/u/60245796?s={AVATAR_PX}"] * len(noreply)
  code, headers, raw = ui.request("GET", f"/api/avatars/{keys.pop()}")
  assert code == 200
  assert headers["content-type"] == "image/png"
  assert raw == PNG
  assert ui.status("GET", "/api/avatars/0123456789abcdef") == 404


def test_any_other_address_costs_one_gh_call(
  tmp_path: Path, pictures: Pictures, monkeypatch: pytest.MonkeyPatch
) -> None:
  sys.path.insert(0, str(ROOT))
  from ui import server

  calls: list[list[str]] = []

  def fake_gh(argv: list[str], **_: Any) -> tuple[int, str, str]:
    calls.append(argv)
    return 0, pictures.url + "/u/7?v=4\n", ""

  monkeypatch.setattr(server, "run_cmd", fake_gh)
  monkeypatch.setattr(server.shutil, "which", lambda name: "/usr/bin/gh")
  store = server.Avatars(tmp_path / "avatars")
  downloads = len(pictures.hits)
  sha = "b" * 40
  key = store.resolve({"other@example.com": sha}, lambda: "demo/shop-web")
  assert key["other@example.com"]
  assert calls == [
    ["gh", "api", f"repos/demo/shop-web/commits/{sha}", "--jq", ".author.avatar_url"]
  ]
  assert pictures.hits[-1] == f"/u/7?v=4&s={server.AVATAR_PX}"
  store.resolve({"other@example.com": "c" * 40}, lambda: "demo/shop-web")
  assert len(calls) == 1 and len(pictures.hits) == downloads + 1, (
    "one lookup per address"
  )


def test_a_picture_lives_thirty_days_after_its_last_use(
  tmp_path: Path, pictures: Pictures, monkeypatch: pytest.MonkeyPatch
) -> None:
  sys.path.insert(0, str(ROOT))
  from ui import server

  monkeypatch.setattr(server, "AVATAR_HOST", pictures.url)
  root = tmp_path / "avatars"
  index = root / "index.json"
  store = server.Avatars(root)
  key = store.resolve({ME_EMAIL: "a" * 40}, lambda: "")[ME_EMAIL]
  assert key and (root / key).exists()
  downloads = len(pictures.hits)
  first = json.loads(index.read_text())[key]["expires"]
  assert first > time.time() + server.AVATAR_TTL - 60

  # a use inside the window moves the expiry forward and downloads nothing
  entries = json.loads(index.read_text())
  entries[key]["expires"] = time.time() + 86400
  index.write_text(json.dumps(entries))
  store = server.Avatars(root)
  assert store.resolve({ME_EMAIL: "a" * 40}, lambda: "")[ME_EMAIL] == key
  assert json.loads(index.read_text())[key]["expires"] > first - 60
  assert len(pictures.hits) == downloads

  # past the window the picture goes, and its next use fetches it again
  entries = json.loads(index.read_text())
  entries[key]["expires"] = time.time() - 1
  index.write_text(json.dumps(entries))
  store = server.Avatars(root)
  other = store.resolve({"other@example.com": "b" * 40}, lambda: "")
  assert other["other@example.com"] is None
  assert not (root / key).exists()
  assert store.resolve({ME_EMAIL: "a" * 40}, lambda: "")[ME_EMAIL] == key
  assert len(pictures.hits) == downloads + 1

  # the server asks for an address without a picture once a day, not once a request
  miss = json.loads(index.read_text())[server.Avatars.key("other@example.com")]
  assert miss["type"] == ""
  assert time.time() < miss["expires"] <= time.time() + server.AVATAR_MISS_TTL


def test_the_tree_route_lists_one_level_of_head(
  ui: UI, world: World, ids: dict[str, str]
) -> None:
  for rel, text in TREE_FILES.items():
    target = world.work / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
  world.git("add", "-A")
  world.commit(
    "other-dev", "other@example.com", "2024-01-06T10:00:00+08:00", "docs: a tree\n"
  )
  repo = ids["repo"]

  root = ui.get(f"/api/repos/{repo}/tree")
  assert root["path"] == ""
  names = [e["name"] for e in root["entries"]]
  assert names.index("docs") < names.index("notes.txt"), "directories sort first"
  types = {e["name"]: e["type"] for e in root["entries"]}
  assert types["docs"] == "dir"
  assert types["notes.txt"] == "file"
  sizes = {e["name"]: e["size"] for e in root["entries"]}
  assert sizes["notes.txt"] == len(TREE_FILES["notes.txt"])

  docs = ui.get(f"/api/repos/{repo}/tree?path=/docs/")
  assert docs["path"] == "docs"
  assert [(e["name"], e["type"]) for e in docs["entries"]] == [("guide.md", "file")]

  assert ui.status("GET", f"/api/repos/{repo}/tree?path=..") == 400
  assert ui.status("GET", f"/api/repos/{repo}/tree?path=docs/../..") == 400
  assert ui.status("GET", f"/api/repos/{repo}/tree?path=nope") == 404
  assert ui.status("GET", f"/api/repos/{repo}/tree?path=notes.txt") == 404
  assert ui.status("GET", "/api/repos/deadbeef1234/tree") == 404

  page = ui.text("/")
  assert 'id="browse"' in page
  assert 'id="tree" role="tree"' in page
  assert 'id="start" data-state="idle"' in page, "one run button with two states"
  assert not re.search(r"options-fold|options-sum|fold-head|<details", page), (
    "the options card does not fold"
  )
  cards = [
    page.index(f'id="{c}"') for c in ("run-card", "options-card", "console-card")
  ]
  assert cards == sorted(cards), "run card, options card, then the log card"


PAGE = ROOT / "ui" / "static" / "index.html"
TEXT_CONTRAST = 4.5


def luminance(colour: str) -> float:
  def channel(hex2: str) -> float:
    c = int(hex2, 16) / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

  r, g, b = (channel(colour[i : i + 2]) for i in (1, 3, 5))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_the_primary_button_fill_reads_under_white() -> None:
  page = PAGE.read_text(encoding="utf-8")
  tokens = dict(re.findall(r"--([a-z0-9-]+): (#[0-9a-f]{6});", page))
  assert "background: var(--accent-deep); border-color" in page
  assert ".btn.primary:hover { background: var(--accent-deep-hi); }" in page
  for name in ("accent-deep", "accent-deep-hi"):
    ratio = 1.05 / (luminance(tokens[name]) + 0.05)
    assert ratio >= TEXT_CONTRAST, f"--{name} {tokens[name]} gives {ratio:.2f}:1"
  assert luminance(tokens["accent-deep-hi"]) < luminance(tokens["accent-deep"])


def test_the_log_clock_reads_on_the_card() -> None:
  page = PAGE.read_text(encoding="utf-8")
  tokens = dict(re.findall(r"--([a-z0-9-]+): (#[0-9a-f]{6});", page))
  assert ".log-row .t { color: var(--dim); }" in page
  ratio = (luminance(tokens["dim"]) + 0.05) / (luminance(tokens["surface"]) + 0.05)
  assert ratio >= TEXT_CONTRAST, f"--dim on --surface gives {ratio:.2f}:1"


ICON_KEY_RE = re.compile(r'^    "?([a-z-]+)"?: svg\(', re.MULTILINE)
GLYPH_ONLY = {"commits-refresh": "Reload commits", "copy": "Copy log"}
GLYPH_BUTTONS = {
  "commits-refresh": "refresh-cw",
  "browse": "folder-tree",
  "copy": "copy",
}


def test_every_icon_name_on_the_page_is_vendored() -> None:
  page = PAGE.read_text(encoding="utf-8")
  vendored = set(ICON_KEY_RE.findall(page))
  used = set(re.findall(r'data-icon="([a-z-]+)"', page)) | set(
    re.findall(r'icon\("([a-z-]+)"', page)
  )
  assert used <= vendored
  assert {"refresh-cw", "copy", "folder-tree"} <= used
  for button_id, glyph in GLYPH_BUTTONS.items():
    match = re.search(rf'<button[^>]*id="{button_id}"[^>]*>(.*?)</button>', page)
    assert match is not None, button_id
    assert f'data-icon="{glyph}"' in match.group(0), button_id
    if button_id in GLYPH_ONLY:
      assert f'aria-label="{GLYPH_ONLY[button_id]}"' in match.group(0)
      assert re.sub(r"<[^>]+>", "", match.group(1)) == ""


CLEAN_GLYPH = (
  '<span class="ico-svg" data-icon="broom-sparkles" aria-hidden="true"></span>'
)


def test_every_clean_button_carries_the_broom_glyph() -> None:
  page = PAGE.read_text(encoding="utf-8")
  for button_id in ("start", "start-mobile"):
    match = re.search(
      rf'<button class="btn primary clean" id="{button_id}"[^>]*>(.*?)</button>', page
    )
    assert match is not None, button_id
    assert match.group(1) == CLEAN_GLYPH + "Clean &amp; Push", button_id
  assert 'class: "btn primary clean", disabled: Boolean(stale) || busy,' in page
  assert 'title: busy ? CLEAN_RUNNING : stale || "Clean & Push",' in page
  assert 'icon("broom-sparkles"), "Clean & Push"));' in page, (
    "the card button has words"
  )
  assert 'running ? ["Cancel"] : [icon("broom-sparkles"), "Clean & Push"]' in page
  assert ".clean .sparkles { opacity: 0;" in page
  assert ".clean:focus-visible .sparkles { opacity: 1; }" in page
  assert "@media (hover: hover) { .clean:hover .sparkles { opacity: 1; } }" in page


WEIGHTS = {400, 520, 560, 600, 620, 640}


def test_the_type_weights_stay_in_the_documented_set() -> None:
  page = PAGE.read_text(encoding="utf-8")
  used = {int(w) for w in re.findall(r"font-weight: (\d+);", page)}
  used |= {int(w) for w in re.findall(r"font: (\d+) ", page)}
  assert used <= WEIGHTS, used - WEIGHTS
  assert "b, strong { font-weight: 600; }" in page


def test_job_links_resolve_to_owner_repo_and_job() -> None:
  sys.path.insert(0, str(ROOT))
  from ui import server

  link = (
    "https://github.com/acme/shop-web/actions/runs/40058751699/job/120767437636?pr=2"
  )
  assert server.job_ref(link) == ("acme", "shop-web", "120767437636")
  assert server.job_ref("https://github.com/acme/shop-web/actions/runs/1") is None
  assert server.job_ref("https://ci.example.com/build/1") is None
  assert server.job_ref("") is None


def test_log_pages_end_at_the_cursor_and_open_on_the_last_page() -> None:
  sys.path.insert(0, str(ROOT))
  from ui import server

  lines = [f"line {n}" for n in range(1000)]
  last = server.log_page(lines, None, 400)
  assert (last["start"], last["total"], len(last["lines"])) == (600, 1000, 400)
  assert last["lines"][-1] == "line 999"
  older = server.log_page(lines, last["start"], 400)
  assert (older["start"], older["lines"][0], older["lines"][-1]) == (
    200,
    "line 200",
    "line 599",
  )
  first = server.log_page(lines, older["start"], 400)
  assert (first["start"], len(first["lines"])) == (0, 200)
  assert server.log_page(lines, 0, 400)["lines"] == []


def test_step_seconds_come_from_the_timestamps() -> None:
  sys.path.insert(0, str(ROOT))
  from ui import server

  done = {"started_at": "2026-10-24T11:24:04Z", "completed_at": "2026-10-24T11:27:19Z"}
  assert server.step_seconds(done) == 195
  assert (
    server.step_seconds({"started_at": "2026-10-24T11:24:04Z", "completed_at": None})
    is None
  )
  assert server.step_seconds({}) is None


def test_the_job_route_reads_steps_and_pages_the_log(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  sys.path.insert(0, str(ROOT))
  from ui import server

  job = {
    "name": "test",
    "status": "completed",
    "conclusion": "failure",
    "html_url": "https://github.com/acme/shop-web/actions/runs/1/job/9",
    "steps": [
      {
        "name": "Set up job",
        "status": "completed",
        "conclusion": "success",
        "started_at": "2026-10-24T11:20:00Z",
        "completed_at": "2026-10-24T11:20:04Z",
      },
      {
        "name": "pytest",
        "status": "completed",
        "conclusion": "failure",
        "started_at": "2026-10-24T11:20:04Z",
        "completed_at": "2026-10-24T11:23:19Z",
      },
    ],
  }
  calls: list[str] = []

  def fake_gh(argv: list[str], **_: Any) -> tuple[int, str, str]:
    calls.append(argv[2])
    if argv[2].endswith("/logs"):
      return 0, "\n".join(f"row {n}" for n in range(1000)), ""
    return 0, json.dumps(job), ""

  monkeypatch.setattr(server, "run_cmd", fake_gh)
  server.JOB_CACHE.clear()
  ref = ("acme", "shop-web", "9")
  report = server.job_report(ref)
  assert report is not None
  assert [s["name"] for s in report["steps"]] == ["Set up job", "pytest"]
  assert [s["seconds"] for s in report["steps"]] == [4, 195]
  assert report["conclusion"] == "failure"
  lines = server.job_log_lines(ref)
  assert lines is not None and len(lines) == 1000
  server.job_log_lines(ref)
  assert calls.count("repos/acme/shop-web/actions/jobs/9/logs") == 1
  server.JOB_CACHE.clear()


def test_a_finished_job_is_read_once_and_a_running_one_again(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  sys.path.insert(0, str(ROOT))
  from ui import server

  status = {"value": "in_progress"}
  calls: list[str] = []

  def fake_gh(argv: list[str], **_: Any) -> tuple[int, str, str]:
    calls.append(argv[2])
    if argv[2].endswith("/logs"):
      return 0, "row 1\nrow 2", ""
    return 0, json.dumps({"name": "test", "status": status["value"], "steps": []}), ""

  monkeypatch.setattr(server, "run_cmd", fake_gh)
  server.JOB_CACHE.clear()
  ref = ("acme", "shop-web", "9")
  job_path = "repos/acme/shop-web/actions/jobs/9"
  for _ in range(2):
    assert server.job_report(ref) == {
      "name": "test",
      "status": "in_progress",
      "conclusion": "",
      "url": "",
      "steps": [],
    }
  assert calls.count(job_path) == 2, "a running job is read on every call"
  assert server.job_log_lines(ref) == ["row 1", "row 2"]
  monkeypatch.setattr(server, "JOB_LOG_TTL", 0.0)
  server.job_log_lines(ref)
  assert calls.count(job_path + "/logs") == 2, "a running job's log follows the TTL"
  status["value"] = "completed"
  calls.clear()
  server.job_report(ref)
  server.job_log_lines(ref)
  assert calls == [job_path, job_path + "/logs"], "the end of a job reads its log again"
  calls.clear()
  assert server.job_report(ref)["status"] == "completed"
  assert server.job_log_lines(ref) == ["row 1", "row 2"]
  assert calls == [], "a finished job and its log come from the kept copy"
  for n in range(server.JOB_CACHE_MAX):
    server.keep_job(("acme", "shop-web", f"1{n:03d}"), job={"status": "completed"})
  assert len(server.JOB_CACHE) == server.JOB_CACHE_MAX
  assert "acme/shop-web/9" not in server.JOB_CACHE, "the oldest job leaves at the cap"
  server.JOB_CACHE.clear()
