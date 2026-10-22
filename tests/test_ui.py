"""The web UI: repo store, one-click jobs, signing, auth, health, and the page shell."""

from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from .conftest import ME_EMAIL, ROOT, World, project_version

SERVER = ROOT / "ui" / "server.py"
STARTUP_SECONDS = 15
JOB_SECONDS = 20
MIN_FONT_BYTES = 20_000
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
        env=self.world.env,
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


@pytest.fixture(scope="module")
def ui(world: World) -> UI:
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
  assert env["tool"] == project_version()
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
  assert "fonts/inter.woff2" in page
  code, headers, font = ui.request("GET", "/fonts/inter.woff2")
  assert code == 200
  assert headers["content-type"] == "font/woff2"
  assert len(font) > MIN_FONT_BYTES
  assert 'id="view-settings"' in page
  assert 'id="view-dashboard"' in page


def test_add_by_path(ui: UI, world: World, ids: dict[str, str]) -> None:
  added = ui.post("/api/repos", {"source": str(world.work)})
  ids["repo"] = added["id"]
  assert added["id"]
  assert ui.post("/api/repos", {"source": str(world.work)})["id"] == added["id"]
  assert len(ui.get("/api/repos")) == 1
  assert added["status"]["ok"] is True, added
  assert added["status"]["default"] == "main"
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
  # give the bare repo one arena branch so the clone has something to report
  world.git(
    f"--git-dir={bare}",
    "update-ref",
    "refs/heads/arena/ui-test",
    "refs/heads/main",
    cwd=world.root,
  )
  clone = ui.post("/api/repos", {"source": f"file://{bare}"})
  ids["clone"] = clone["id"]
  ids["clone_path"] = clone["path"]
  assert clone["managed"] is True
  assert (Path(clone["path"]) / ".git").is_dir()
  assert clone["status"]["default"] == "main"
  assert any(b.startswith("arena/") for b in clone["status"]["arena"])
  assert len(ui.get("/api/repos")) == 2
  assert ui.status("POST", "/api/repos", {"source": "/nope/nope"}) == 400
  assert ui.status("POST", "/api/repos", {"source": "  "}) == 400
  assert ui.status("GET", "/api/repos/deadbeef1234") == 404


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


def test_reset_to_origin(ui: UI, world: World, ids: dict[str, str]) -> None:
  world.git("checkout", "-q", "main")
  world.commit("someone", "someone@example.com", "2024-02-01T10:00:00+08:00", "wip")
  (world.work / "scratch.txt").write_text("untracked\n")
  assert world.rev() != world.rev("origin/main")

  out = ui.post(f"/api/repos/{ids['repo']}/reset", {})
  assert out["reset"] == "origin/main"
  assert out["status"]["branch"] == "main"
  assert out["status"]["ahead"] == 0
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
  assert ui.status("POST", jobs, {"action": "run", "branch": "--upload-pack=x"}) == 400
  assert ui.status("POST", jobs, {"action": "run", "paths": ["-x"]}) == 400
  assert ui.status("POST", jobs, {"action": "strip"}) == 400, "strip is CLI only"
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
  # "these branches have no pull request".
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
  for icon in ("icon-192.png", "icon-512.png", "apple-touch-icon.png"):
    code, _, raw = ui.request("GET", f"/icons/{icon}")
    assert code == 200 and raw[:4] == PNG_MAGIC, icon
  code, headers, raw = ui.request("GET", "/sw.js")
  assert headers["content-type"] == "application/javascript; charset=utf-8"
  assert "no-store" in headers["cache-control"]
  assert headers["service-worker-allowed"] == "/"
  worker = raw.decode()
  assert "arena-shell" in worker
  assert 'url.pathname.startsWith("/api/")' in worker, "the worker caches API responses"
  assert "apple-mobile-web-app-capable" in page
  assert "serviceWorker.register" in page


def test_the_icon_licence_ships_beside_the_page(ui: UI) -> None:
  code, _, raw = ui.request("GET", "/LICENSE-lucide.txt")
  assert code == 200
  assert raw.startswith(b"ISC License")


def test_repos_survive_a_restart_and_can_be_forgotten(
  ui: UI, ids: dict[str, str]
) -> None:
  ui.stop()
  ui.start()
  repos = ui.get("/api/repos")
  assert len(repos) == 2
  assert repos[0]["status"]["ok"] is True
  removed = ui.post(f"/api/repos/{ids['clone']}/remove", {"delete": True})
  assert removed["removed"] == ids["clone"]
  assert len(ui.get("/api/repos")) == 1
  assert not Path(ids["clone_path"]).exists()


COMMIT_FIELDS = {"sha", "short", "subject", "author", "date", "signed"}
SHORT_SHA = 7


def test_the_commit_list_and_the_page_shell(ui: UI, ids: dict[str, str]) -> None:
  repo = ids["repo"]
  commits = ui.get(f"/api/repos/{repo}/commits?limit=2")
  assert len(commits["commits"]) == 2
  assert commits["total"] >= 2
  assert all(COMMIT_FIELDS <= set(c) for c in commits["commits"])
  assert len(commits["commits"][0]["short"]) >= SHORT_SHA
  assert commits["branch"] != ""
  assert len(ui.get(f"/api/repos/{repo}/commits?limit=0")["commits"]) == 1
  assert ui.status("GET", f"/api/repos/{repo}/commits?limit=100000") == 200
  assert ui.status("GET", f"/api/repos/{repo}/commits?limit=abc") == 200
  assert ui.status("GET", "/api/repos/deadbeef1234/commits") == 404

  page = ui.text("/")
  assert 'id="commits"' in page
  assert 'id="logwrap" hidden' in page, "the log does not start collapsed"
  assert 'id="phases"' in page
  assert 'class="brand" href="#/"' in page
  assert 'id="task-note"' in page
  assert 'id="start-mobile"' in page
  assert not re.search(
    r'cmdpreview|id="cmdline"|id="emptystate"|oneclick-mobile|cmdswitch|data-cmd=', page
  ), "the removed command strip and switch"
