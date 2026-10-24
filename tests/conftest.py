"""Shared fixtures: a bare origin, a work clone, a fake gh, and the engine CLI.

The engine tests share one scratch world and run in file order. Each test
builds on the repo state the earlier tests left behind, as the original
end-to-end suite did. Log assertions use the key tokens of a message (branch,
sha, count, flag, check name), not full sentences.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "arena-cleanup.py"
ME_EMAIL = "60245796+nemoe7@users.noreply.github.com"
SEED_COMMITS = 5
LOG_LINE = re.compile(
  r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2} (INFO|OK|WARN|ERROR) "
)
# a verbatim dump line, a blank line, or a timestamped line. Anything else is stray noise
EXPECTED_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2}T|  \| | *$)")


def _check(
  name: str, status: str = "COMPLETED", conclusion: str = "SUCCESS"
) -> dict[str, str]:
  return {"name": name, "status": status, "conclusion": conclusion}


def _rollup(checks: list[dict[str, str]]) -> str:
  return json.dumps({"statusCheckRollup": checks}, separators=(",", ":"))


GREEN = [_check("build"), _check("test")]
ROLLUPS = {
  "failing": [_check("build"), _check("test", conclusion="FAILURE")],
  "superseded": [
    _check("build", conclusion="CANCELLED"),
    _check("build"),
    _check("test"),
  ],
  "superseded-failing": [
    _check("build", conclusion="CANCELLED"),
    _check("build"),
    _check("test", conclusion="FAILURE"),
  ],
  "pending-forever": [_check("build", "IN_PROGRESS", "")],
}
AUTH_JSON = json.dumps(
  {
    "hosts": {
      "github.com": [
        {
          "state": "success",
          "active": True,
          "host": "github.com",
          "login": "nemoe7",
          "tokenSource": "oauth_token",
          "scopes": "repo, read:org",
        }
      ]
    }
  },
  separators=(",", ":"),
)

# fake gh: PR state driven by files so tests can flip it
FAKE_GH_TEMPLATE = r"""#!/usr/bin/env bash
state_file="${FAKE_GH_STATE:-/tmp/fake-gh-state}"
if [ "$1 $2" = "pr list" ]; then
  if [ "$(cat "$state_file" 2>/dev/null)" = "none" ]; then
    echo '[]'
  else
    echo '[{"number":42}]'
  fi
  exit 0
fi
if [ "$1 $2" = "pr view" ]; then
  state="$(cat "$state_file" 2>/dev/null)"
  case "$state" in
    pending)
      # in progress for the first poll, then green - exercises the waiting path
      n="$(cat "$state_file.count" 2>/dev/null || echo 0)"; n=$((n+1)); echo "$n" > "$state_file.count"
      if [ "$n" -ge 2 ]; then
        echo '@PENDING_DONE@'
      else
        echo '@PENDING_RUNNING@'
      fi ;;
    bad-shape)
      # a wrapper around gh printing a bare list: gh never does, a wrapper can
      echo '@BAD_SHAPE@' ;;
    none)
      echo '[]' ;;
@CASES@    *)
      echo '@GREEN@' ;;
  esac
  exit 0
fi
if [ "$1 $2" = "auth status" ]; then
  if [ "$(cat "$state_file.auth" 2>/dev/null)" = "out" ]; then
    echo "You are not logged into any GitHub hosts." >&2
    exit 1
  fi
  if [ "$3" = "--json" ]; then
    echo '@AUTH@'
  else
    echo "github.com"
    echo "  ✓ Logged in to github.com account nemoe7 (keyring)"
  fi
  exit 0
fi
if [ "$1 $2" = "auth login" ]; then cat >"$state_file.stdin"; exit 0; fi
if [ "$1 $2" = "auth setup-git" ]; then exit 0; fi
if [ "$1 $2" = "pr status" ]; then exit 0; fi
echo "fake gh: unhandled: $*" >&2; exit 1
"""


def fake_gh_script() -> str:
  cases = "".join(
    f"    {state})\n      echo '{_rollup(checks)}' ;;\n"
    for state, checks in ROLLUPS.items()
  )
  return (
    FAKE_GH_TEMPLATE.replace("@CASES@", cases)
    .replace("@PENDING_DONE@", _rollup([_check("build")]))
    .replace("@PENDING_RUNNING@", _rollup([_check("build", "IN_PROGRESS", "")]))
    .replace("@BAD_SHAPE@", json.dumps([_check("build")], separators=(",", ":")))
    .replace("@GREEN@", _rollup(GREEN))
    .replace("@AUTH@", AUTH_JSON)
  )


GITCONFIG = f"""[user]
    name = nemoe7
    email = {ME_EMAIL}
[init]
    defaultBranch = main
[commit]
    gpgsign = false
[advice]
    detachedHead = false
"""


def project_version() -> str:
  """The UI version, from pyproject.toml."""
  with open(ROOT / "pyproject.toml", "rb") as fh:
    return tomllib.load(fh)["project"]["version"]


def engine_version() -> str:
  """The engine version, the `__version__` constant in arena-cleanup.py."""
  match = re.search(r'^__version__ = "([^"]*)"$', ENGINE.read_text(), re.MULTILINE)
  assert match, "arena-cleanup.py carries no __version__ line"
  return match.group(1)


@dataclass
class Result:
  """One engine invocation: exit code, merged output, and wall time."""

  rc: int
  text: str
  seconds: float

  @property
  def lines(self) -> list[str]:
    return self.text.splitlines()

  def says(self, *tokens: str) -> bool:
    """True when one output line carries every token."""
    return any(all(t in line for t in tokens) for line in self.lines)

  def count(self, token: str) -> int:
    return sum(token in line for line in self.lines)

  def strays(self) -> list[str]:
    return [line for line in self.lines if not EXPECTED_LINE.match(line)]


class World:
  """A scratch directory with a bare origin, a work clone, and a fake gh."""

  def __init__(self, root: Path) -> None:
    self.root = root
    self.bin = root / "bin"
    self.origin = root / "origin.git"
    self.work = root / "work"
    self.tmp = root / "tmp"
    self.gh_state_file = root / "gh-state"
    self.gnupghome = root / "gnupg"
    self.key_id = ""
    self.env = dict(os.environ)
    for d in (self.bin, self.tmp):
      d.mkdir(parents=True)
    self._write_tools()
    self.env.update(
      PYTHONIOENCODING="utf-8",
      TMPDIR=str(self.tmp),
      GIT_CONFIG_GLOBAL=str(root / "gitconfig"),
      FAKE_GH_STATE=str(self.gh_state_file),
      PATH=f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}",
    )
    (root / "gitconfig").write_text(GITCONFIG)
    self._make_key()
    self._seed()

  # -- construction -----------------------------------------------------------

  def _write_tools(self) -> None:
    gh = self.bin / "gh"
    gh.write_text(fake_gh_script())
    gh.chmod(0o755)
    shim = self.bin / "arena-cleanup"
    shim.write_text(f'#!/usr/bin/env bash\nexec "{sys.executable}" "{ENGINE}" "$@"\n')
    shim.chmod(0o755)

  def _make_key(self) -> None:
    if shutil.which("gpg") is None:
      return
    self.gnupghome.mkdir()
    self.gnupghome.chmod(0o700)
    self.env["GNUPGHOME"] = str(self.gnupghome)
    subprocess.run(
      [
        "gpg",
        "--batch",
        "--quiet",
        "--passphrase",
        "",
        "--quick-generate-key",
        "Test Signer <signer@example.com>",
        "default",
        "default",
        "0",
      ],
      env=self.env,
      capture_output=True,
      check=False,
    )
    listing = subprocess.run(
      ["gpg", "--list-secret-keys", "--with-colons"],
      env=self.env,
      capture_output=True,
      text=True,
      check=False,
    ).stdout
    for line in listing.splitlines():
      if line.startswith("sec:"):
        self.key_id = line.split(":")[4]
        break

  def _seed(self) -> None:
    self.origin.mkdir()
    self.git("init", "--bare", "-q", "-b", "main", str(self.origin), cwd=self.root)
    self.git("clone", "-q", str(self.origin), str(self.work), cwd=self.root)
    if self.key_id:
      self.git("config", "user.signingkey", self.key_id)
      self.git("config", "gpg.program", "gpg")
    other = ("other-dev", "other@example.com")
    self.commit(*other, "2024-01-01T10:00:00+08:00", "chore: init\n")
    self.git("push", "-q", "-u", "origin", "main")
    self.git("checkout", "-q", "-b", "arena/session-1")
    self.commit(
      *other,
      "2024-01-02T10:00:00+08:00",
      "feat: external contribution\n\nbody the human wrote\n",
    )
    self.commit(
      "arena-agent",
      "agent@arena.ai",
      "2024-01-03T10:00:00+08:00",
      "feat: agent work\n\nlong body that should be trimmed\n",
    )
    self.commit(
      "nemoe7", ME_EMAIL, "2024-01-04T10:00:00+08:00", "fix: mine already fine\n"
    )
    self.commit(
      "arena-ai-coding-agent[bot]",
      "bot@arena.ai",
      "2024-01-05T10:00:00+08:00",
      "chore: bot cleanup\n\nanother body to trim\n",
    )
    self.git("push", "-q", "-u", "origin", "arena/session-1")
    self.git("checkout", "-q", "main")
    # a stale local arena branch that is NOT on origin
    self.git("branch", "arena/stale", "main")
    self.old_tip = self.rev("arena/session-1")
    self.orig_m1 = self.rev("arena/session-1~3")
    self.orig_m0 = self.rev("main")
    self.author_date_agent = self.git("log", "-1", "--format=%aI", "arena/session-1~2")

  # -- helpers ----------------------------------------------------------------

  def git(
    self,
    *args: str,
    cwd: Path | None = None,
    check: bool = True,
    env: dict[str, str] | None = None,
  ) -> str:
    proc = subprocess.run(
      ["git", *args],
      cwd=cwd or self.work,
      env=env or self.env,
      capture_output=True,
      text=True,
      check=False,
    )
    if check and proc.returncode != 0:
      raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()

  def git_rc(self, *args: str, cwd: Path | None = None) -> int:
    return subprocess.run(
      ["git", *args],
      cwd=cwd or self.work,
      env=self.env,
      capture_output=True,
      check=False,
    ).returncode

  def rev(self, ref: str = "HEAD", cwd: Path | None = None) -> str:
    return self.git("rev-parse", ref, cwd=cwd)

  def has_ref(self, ref: str, cwd: Path | None = None) -> bool:
    return (
      subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", ref],
        cwd=cwd or self.work,
        env=self.env,
        check=False,
      ).returncode
      == 0
    )

  def remote_heads(self, cwd: Path | None = None) -> list[str]:
    out = self.git("ls-remote", "--heads", "origin", cwd=cwd)
    return [
      line.split("refs/heads/", 1)[1]
      for line in out.splitlines()
      if "refs/heads/" in line
    ]

  def commit(
    self, name: str, email: str, date: str, message: str, cwd: Path | None = None
  ) -> None:
    env = dict(self.env)
    env.update(
      GIT_AUTHOR_NAME=name,
      GIT_AUTHOR_EMAIL=email,
      GIT_AUTHOR_DATE=date,
      GIT_COMMITTER_NAME=name,
      GIT_COMMITTER_EMAIL=email,
      GIT_COMMITTER_DATE=date,
    )
    self.git(
      "commit", "-q", "--allow-empty", "-m", message, "--no-gpg-sign", cwd=cwd, env=env
    )

  def agent_commit(self, subject: str, cwd: Path | None = None) -> None:
    self.git(
      "commit",
      "-q",
      "--allow-empty",
      "-m",
      subject,
      "--author=arena-agent <agent@arena.ai>",
      "--no-gpg-sign",
      cwd=cwd,
    )

  def only_arena(self, keep: str = "", cwd: Path | None = None) -> None:
    """Leave exactly one origin/arena/* branch behind so discovery is unambiguous."""
    for branch in self.remote_heads(cwd):
      if branch.startswith("arena/") and branch != keep:
        self.git("push", "-q", "origin", "--delete", branch, cwd=cwd)
    self.git("fetch", "-q", "--prune", "origin", cwd=cwd)

  def gh_state(self, state: str, reset_count: bool = True) -> None:
    self.gh_state_file.write_text(state + "\n")
    if reset_count:
      Path(f"{self.gh_state_file}.count").unlink(missing_ok=True)

  def gh_auth(self, signed_in: bool) -> None:
    flag = Path(f"{self.gh_state_file}.auth")
    if signed_in:
      flag.unlink(missing_ok=True)
    else:
      flag.write_text("out\n")

  def cleanup(
    self,
    *args: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    stdin: str | None = None,
    timeout: int = 180,
  ) -> Result:
    """Run the engine CLI as the shim does and capture its merged output."""
    started = time.monotonic()
    proc = subprocess.run(
      [sys.executable, str(ENGINE), *args],
      cwd=cwd or self.work,
      env=env or self.env,
      input=stdin if stdin is not None else "",
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
      errors="replace",
      timeout=timeout,
      check=False,
    )
    return Result(proc.returncode, proc.stdout, time.monotonic() - started)

  def interactive(
    self, command: str, answer: str, cwd: Path | None = None, timeout: int = 120
  ) -> Result:
    """Run a shell command under a pseudo-terminal and answer its prompt."""
    started = time.monotonic()
    proc = subprocess.run(
      ["script", "-qec", command, "/dev/null"],
      cwd=cwd or self.work,
      env=self.env,
      input=answer,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
      errors="replace",
      timeout=timeout,
      check=False,
    )
    return Result(proc.returncode, proc.stdout, time.monotonic() - started)


@pytest.fixture(scope="session")
def world(tmp_path_factory: pytest.TempPathFactory) -> World:
  return World(tmp_path_factory.mktemp("arena"))


def pytest_configure(config: pytest.Config) -> None:
  config.addinivalue_line(
    "markers", "e2e: drives a real browser against a demo instance"
  )
