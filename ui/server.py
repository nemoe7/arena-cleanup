#!/usr/bin/env python3
"""
arena-ui - the web front end for arena-cleanup.

Serves a dashboard of remembered repositories and runs the CLI against them.
Every button press becomes an argv, never a shell string. The process output
streams straight back to the browser. Nothing about the rewrite logic lives
here: arena-cleanup.py stays the only thing that touches git.

    python3 ui/server.py [--data DIR] [--port 8080]

Environment: ARENA_DATA, ARENA_PORT, ARENA_HOST.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tomllib
import urllib.parse
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any

UI_DIR = Path(__file__).resolve().parent
TOOL = UI_DIR.parent / "arena-cleanup.py"
STATIC = UI_DIR / "static"


def load_tool() -> ModuleType:
  """The CLI as a module: its constants are the settings page's fallbacks."""
  spec = importlib.util.spec_from_file_location("arena_cleanup", TOOL)
  if spec is None or spec.loader is None:
    raise ImportError(f"cannot load {TOOL}")
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


engine = load_tool()


def project_version() -> str:
  """The version from pyproject.toml, the one place it is set."""
  with (UI_DIR.parent / "pyproject.toml").open("rb") as fh:
    return tomllib.load(fh)["project"]["version"]


VERSION = project_version()

COMMANDS = {"run"}
MAX_LINES = 4000
STATUS_TTL = 8.0  # seconds a repo status is reused before asking git again
STARTED = time.time()  # when this process came up, for /healthz
GIT_TIMEOUT = 20
URL_RE = re.compile(r"^(git@|ssh://|https?://|git://|file://)")
GITHUB_WEB_RE = re.compile(
  r"^(?:https?://)?(?:www\.)?github\.com/([^/\s]+)/([^/\s?#]+)", re.IGNORECASE
)


def tool_version() -> str:
  try:
    out = subprocess.run(
      [sys.executable, str(TOOL), "-V"],
      capture_output=True,
      text=True,
      check=False,
      timeout=20,
    )
    return out.stdout.strip().split()[-1] if out.returncode == 0 else "?"
  except (OSError, subprocess.SubprocessError):
    return "?"


def run_cmd(
  argv: list[str],
  cwd: str | None = None,
  timeout: int = GIT_TIMEOUT,
  stdin_text: str | None = None,
) -> tuple[int, str, str]:
  """(returncode, stdout, stderr) - never raises for a non-zero exit.

  Anything secret goes through `stdin_text`, never through argv. A token in a
  command line is visible to every process on the box.
  """
  opts: dict[str, Any] = {
    "cwd": cwd,
    "capture_output": True,
    "text": True,
    "timeout": timeout,
  }
  if stdin_text is None:
    opts["stdin"] = subprocess.DEVNULL
  else:
    opts["input"] = stdin_text
  try:
    out = subprocess.run(argv, check=False, **opts)
    return out.returncode, out.stdout.strip(), out.stderr.strip()
  except subprocess.TimeoutExpired:
    return 124, "", f"timed out after {timeout}s: {' '.join(argv[:3])}"
  except OSError as exc:
    return 127, "", str(exc)


def git(*args: str, cwd: str | None = None, timeout: int = GIT_TIMEOUT) -> str:
  rc, out, _ = run_cmd(["git", *args], cwd=cwd, timeout=timeout)
  return out if rc == 0 else ""


# --------------------------------------------------------------------------- #
# Registry - the repositories this instance remembers
# --------------------------------------------------------------------------- #


class Registry:
  """
  A JSON file of known repositories, written atomically.

  Small enough that a lock around every operation is cheaper than reasoning
  about interleavings. It is read on every request.
  """

  def __init__(self, data_dir: Path) -> None:
    self.data = data_dir
    self.path = data_dir / "repos.json"
    self.clones = data_dir / "repos"
    self.clones.mkdir(parents=True, exist_ok=True)
    self._lock = threading.Lock()

  def _read(self) -> list[dict[str, Any]]:
    try:
      with open(self.path, encoding="utf-8") as handle:
        data = json.load(handle)
      return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
      return []

  def _write(self, repos: list[dict[str, Any]]) -> None:
    tmp = self.path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
      json.dump(repos, handle, indent=2)
      handle.write("\n")
    os.replace(tmp, self.path)

  def all(self) -> list[dict[str, Any]]:
    with self._lock:
      return self._read()

  def get(self, repo_id: str) -> dict[str, Any] | None:
    return next((r for r in self.all() if r["id"] == repo_id), None)

  def add(self, entry: dict[str, Any]) -> dict[str, Any]:
    with self._lock:
      repos = self._read()
      existing = next((r for r in repos if r["path"] == entry["path"]), None)
      if existing:
        return existing
      repos.append(entry)
      self._write(repos)
      return entry

  def remove(self, repo_id: str) -> dict[str, Any] | None:
    with self._lock:
      repos = self._read()
      found = next((r for r in repos if r["id"] == repo_id), None)
      if found:
        self._write([r for r in repos if r["id"] != repo_id])
      return found


def repo_id(path: str) -> str:
  import hashlib

  return hashlib.sha1(os.path.realpath(path).encode()).hexdigest()[:12]


def normalize_source(source: str) -> str:
  """Turn a pasted GitHub page address into its clone URL; leave anything else alone."""
  match = GITHUB_WEB_RE.match(source.strip())
  if not match:
    return source.strip()
  owner, name = match.groups()
  return f"https://github.com/{owner}/{name.removesuffix('.git')}.git"


def repo_name(source: str) -> str:
  tail = source.rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
  tail = tail.removesuffix(".git")
  return tail or "repo"


def clone_url(url: str, reg: Registry) -> tuple[dict[str, Any] | None, str]:
  """Clone into the managed directory; returns (entry, error)."""
  name = repo_name(url)
  target = reg.clones / name
  if target.exists():
    suffix = 2
    while (reg.clones / f"{name}-{suffix}").exists():
      suffix += 1
    name = f"{name}-{suffix}"
    target = reg.clones / name
  rc, _, err = run_cmd(["git", "clone", "--quiet", url, str(target)], timeout=600)
  if rc != 0:
    shutil.rmtree(target, ignore_errors=True)
    return None, err or "git clone failed"
  return register_path(str(target), reg, source=url, managed=True)


def register_path(
  path: str, reg: Registry, *, source: str = "", managed: bool = False
) -> tuple[dict[str, Any] | None, str]:
  real = os.path.realpath(os.path.expanduser(path))
  if not os.path.isdir(real):
    return None, f"no such directory: {path}"
  if git("rev-parse", "--is-inside-work-tree", cwd=real) != "true":
    return None, f"not a git work tree: {path}"
  root = git("rev-parse", "--show-toplevel", cwd=real) or real
  entry = {
    "id": repo_id(root),
    "path": root,
    "name": os.path.basename(root),
    "source": source or root,
    "managed": managed,
  }
  return reg.add(entry), ""


# --------------------------------------------------------------------------- #
# Status - what the dashboard shows for each repo
# --------------------------------------------------------------------------- #


class StatusCache:
  def __init__(self) -> None:
    self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
    self._lock = threading.Lock()

  def get(self, repo: dict[str, Any]) -> dict[str, Any]:
    key = repo["id"] + ":" + repo["path"]
    with self._lock:
      hit = self._cache.get(key)
      if hit and time.time() - hit[0] < STATUS_TTL:
        return hit[1]
    value = repo_status(repo)
    with self._lock:
      self._cache[key] = (time.time(), value)
    return value

  def drop(self, repo_id: str) -> None:
    with self._lock:
      for key in [k for k in self._cache if k.startswith(repo_id + ":")]:
        del self._cache[key]

  def clear(self) -> None:
    with self._lock:
      self._cache.clear()


STATUS = StatusCache()


def pr_checks(branch: str, cwd: str) -> dict[str, Any] | None:
  """Open PR for this branch and its check rollup, via one gh call."""
  if not shutil.which("gh"):
    return None
  rc, out, _ = run_cmd(
    [
      "gh",
      "pr",
      "list",
      "--head",
      branch,
      "--state",
      "open",
      "--json",
      "number,title,url,statusCheckRollup",
      "--limit",
      "1",
    ],
    cwd=cwd,
    timeout=25,
  )
  if rc != 0 or not out:
    return None
  try:
    prs = json.loads(out)
  except json.JSONDecodeError:
    return None
  if not isinstance(prs, list) or not prs:
    return None
  pr = prs[0]
  runs = pr.get("statusCheckRollup") or []
  passed = failed = running = 0
  for run in runs:
    state = (run.get("state") or run.get("conclusion") or "").upper()
    status = (run.get("status") or "").upper()
    if status in {"IN_PROGRESS", "QUEUED", "PENDING", ""} and state not in {
      "SUCCESS",
      "FAILURE",
      "ERROR",
      "CANCELLED",
      "SKIPPED",
      "NEUTRAL",
    }:
      running += 1
    elif state in {"SUCCESS", "SKIPPED", "NEUTRAL"}:
      passed += 1
    elif state in {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"}:
      failed += 1
    else:
      running += 1
  return {
    "number": pr.get("number"),
    "title": pr.get("title", ""),
    "url": pr.get("url", ""),
    "total": len(runs),
    "passed": passed,
    "failed": failed,
    "running": running,
    "state": "failing"
    if failed
    else ("running" if running else ("passing" if runs else "none")),
  }


def default_branch(cwd: str) -> str:
  head = git("symbolic-ref", "refs/remotes/origin/HEAD", cwd=cwd)
  if head.startswith("refs/remotes/origin/"):
    return head[len("refs/remotes/origin/") :]
  for line in git("ls-remote", "--symref", "origin", "HEAD", cwd=cwd).splitlines():
    if line.startswith("ref:") and "/heads/" in line:
      return line.split("refs/heads/", 1)[1].split()[0]
  for candidate in ("main", "master"):
    if git("rev-parse", "--verify", "-q", f"origin/{candidate}", cwd=cwd):
      return candidate
  return ""


def reset_to_origin(repo: dict[str, Any]) -> str:
  """Put the clone back on the default branch at origin's tip; untracked files stay."""
  cwd = repo["path"]
  for job in JOBS.values():
    if job.repo["id"] == repo["id"] and job.exit is None:
      raise BadRequest("a run is in progress; cancel it first")
  default = default_branch(cwd)
  if not default:
    raise BadRequest("origin has no default branch")
  run_cmd(["git", "rebase", "--abort"], cwd=cwd)
  steps = (
    ["git", "fetch", "--prune", "origin"],
    ["git", "checkout", "-q", "--force", default],
    ["git", "reset", "--hard", "-q", f"origin/{default}"],
  )
  for argv in steps:
    rc, _, err = run_cmd(argv, cwd=cwd, timeout=120)
    if rc != 0:
      raise BadRequest(err or f"{' '.join(argv[1:3])} failed")
  return f"origin/{default}"


def repo_status(repo: dict[str, Any]) -> dict[str, Any]:
  cwd = repo["path"]
  if not os.path.isdir(cwd):
    return {"ok": False, "reason": "directory is gone", "path": cwd}
  inside = git("rev-parse", "--is-inside-work-tree", cwd=cwd)
  if inside != "true":
    return {"ok": False, "reason": "not a git work tree", "path": cwd}

  branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd) or "(detached)"
  dirty = [
    ln for ln in git("status", "--porcelain", cwd=cwd).splitlines() if ln.strip()
  ]
  default = default_branch(cwd)

  arena = [
    b[len("origin/") :]
    for b in git(
      "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin", cwd=cwd
    ).splitlines()
    if b.startswith("origin/arena/")
  ]
  ahead = behind = 0
  if default:
    counts = git(
      "rev-list", "--left-right", "--count", f"HEAD...origin/{default}", cwd=cwd
    ).split()
    if len(counts) == 2:
      ahead, behind = (int(counts[0]), int(counts[1]))

  # PR state for each arena branch, bounded. A repo with many branches must
  # not turn one dashboard load into a dozen API calls. `pr_checked` lets the
  # dashboard say "cannot see checks" instead of "no PR" when gh is signed
  # out. Those two look identical in an empty dict and mean different things.
  checks: dict[str, Any] = {}
  gh = auth_report()["gh"]
  authenticated = bool(gh["installed"] and gh["authenticated"])
  if authenticated:
    for name in arena[:4]:
      info = pr_checks(name, cwd)
      if info:
        checks[name] = info

  return {
    "ok": True,
    "path": repo["path"],
    "branch": branch,
    "default": default or "?",
    "dirty": len(dirty),
    "ahead": ahead,
    "behind": behind,
    "arena": arena,
    "pr": checks,
    "pr_checked": authenticated,
    "pr_reason": ""
    if authenticated
    else (
      "gh is not signed in, so pull requests and checks cannot be read"
      if gh["installed"]
      else "gh is not installed, so pull requests and checks cannot be read"
    ),
    "head": git("log", "-1", "--format=%h%x09%s", cwd=cwd),
    "remote": git("config", "--get", "remote.origin.url", cwd=cwd),
  }


# --------------------------------------------------------------------------- #
# Signing - a key in the container, and whether GitHub knows about it
# --------------------------------------------------------------------------- #


def gpg_available() -> bool:
  return bool(shutil.which("gpg"))


def secret_keys() -> list[dict[str, Any]]:
  """Secret keys with fingerprint, uid and capability flags."""
  if not gpg_available():
    return []
  rc, out, _ = run_cmd(["gpg", "--with-colons", "--list-secret-keys"], timeout=20)
  if rc != 0 or not out:
    return []
  keys: list[dict[str, Any]] = []
  current: dict[str, Any] | None = None
  pending_fpr = False
  for line in out.splitlines():
    fields = line.split(":")
    if not fields:
      continue
    record = fields[0]
    if record == "sec":
      current = {
        "fingerprint": "",
        "created": fields[5],
        "expires": fields[6],
        "uid": "",
      }
      keys.append(current)
      pending_fpr = True
    elif (
      record == "fpr"
      and pending_fpr
      and current is not None
      and not current["fingerprint"]
    ):
      current["fingerprint"] = fields[9]
      pending_fpr = False
    elif record == "uid" and current is not None and not current["uid"]:
      current["uid"] = fields[9]
  return [k for k in keys if k["fingerprint"]]


def github_gpg_keys() -> tuple[list[str], str]:
  """(long key ids on the account, error). Empty ids + error when unknown."""
  if not shutil.which("gh"):
    return [], "gh is not installed"
  rc, out, err = run_cmd(
    ["gh", "api", "user/gpg_keys", "--jq", ".[].key_id"], timeout=25
  )
  if rc != 0:
    return [], err or "could not read GitHub keys (is gh authenticated?)"
  return [line.strip().upper() for line in out.splitlines() if line.strip()], ""


def global_config(key: str) -> str:
  return git("config", "--global", key)


def global_config_all(key: str) -> list[str]:
  """Every value of a multi-valued global key, in order; empty when unset."""
  text = git("config", "--global", "--get-all", key)
  return [line.strip() for line in text.splitlines() if line.strip()]


def set_global_config_all(key: str, values: list[str]) -> None:
  rc, _, err = run_cmd(["git", "config", "--global", "--unset-all", key])
  if rc not in (0, 5):  # 5: the key was not set
    raise BadRequest(err or f"could not clear {key}")
  for value in values:
    rc, _, err = run_cmd(["git", "config", "--global", "--add", key, value])
    if rc != 0:
      raise BadRequest(err or f"could not set {key}")


def settings_report() -> dict[str, Any]:
  """The identity and the claim rules a run will use, plus the built-in fallbacks."""
  return {
    "identity": {
      "name": global_config("user.name"),
      "email": global_config("user.email"),
    },
    "claims": {
      "emails": global_config_all("arena.claim-email"),
      "names": global_config_all("arena.claim-name"),
      "defaults": {
        "emails": engine.CLAIM_EMAILS.split(),
        "names": engine.CLAIM_NAMES.split(),
      },
    },
  }


def clean_values(raw: Any, what: str) -> list[str]:
  if not isinstance(raw, list) or not all(isinstance(v, str) for v in raw):
    raise BadRequest(f"{what} must be a list of strings")
  values: list[str] = []
  for value in (v.strip() for v in raw):
    if not value:
      continue
    if "\n" in value or "\r" in value:
      raise BadRequest(f"{what} cannot span lines")
    if value not in values:
      values.append(value)
  return values


def commits_report(repo: dict[str, Any], limit: int = 30) -> dict[str, Any]:
  """The most recent commits on HEAD, with their signature state.

  The run card shows which commits a cleanup produced. This is the git answer,
  read after the run rather than parsed out of the log.
  """
  cwd = repo["path"]
  branch = git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd) or "(detached)"
  total = git("rev-list", "--count", "HEAD", cwd=cwd).strip()
  fmt = "%H%x1f%h%x1f%s%x1f%an%x1f%aI%x1f%G?"
  out = git("log", f"-{limit}", f"--format={fmt}", "HEAD", cwd=cwd)
  commits = []
  for line in out.splitlines():
    fields = line.split("\x1f")
    if len(fields) != 6:
      continue
    sha, short, subject, author, date, sig = fields
    commits.append(
      {
        "sha": sha,
        "short": short,
        "subject": subject,
        "author": author,
        "date": date,
        "signed": sig in ("G", "U"),
      }
    )
  return {
    "branch": branch,
    "total": int(total) if total.isdigit() else len(commits),
    "shown": len(commits),
    "commits": commits,
  }


def tree_report(repo: dict[str, Any], rel: str) -> dict[str, Any] | None:
  """One level of the HEAD tree under `rel`, directories first.

  The path tree reads the clone, not GitHub, so a path repository works
  too. HEAD is the tree the owner sees; a path that only old commits carried
  stays a typed chip. None means git knows no such directory.
  """
  parts = [part for part in rel.split("/") if part]
  if any(part in (".", "..") for part in parts) or "\x00" in rel:
    raise ValueError(rel)
  rel = "/".join(parts)
  rc, out, _ = run_cmd(["git", "ls-tree", "-z", "-l", f"HEAD:{rel}"], cwd=repo["path"])
  if rc != 0:
    return None
  types = {"tree": "dir", "blob": "file", "commit": "submodule"}
  entries = []
  for record in out.split("\0"):
    if "\t" not in record:
      continue
    meta, name = record.split("\t", 1)
    fields = meta.split()
    if len(fields) != 4:
      continue
    mode, obj_type, _sha, size = fields
    entries.append(
      {
        "name": name,
        "type": "link" if mode == "120000" else types.get(obj_type, obj_type),
        "size": int(size) if size.isdigit() else 0,
      }
    )
  entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))
  return {"path": rel, "entries": entries}


def signing_report() -> dict[str, Any]:
  keys = secret_keys()
  git_name = global_config("user.name")
  git_email = global_config("user.email")
  signingkey = global_config("user.signingkey")
  fmt = global_config("gpg.format")
  gh_ids, gh_err = github_gpg_keys()
  for key in keys:
    key["on_github"] = key["fingerprint"][-16:].upper() in gh_ids
  active = next(
    (
      k
      for k in keys
      if signingkey and k["fingerprint"].upper().endswith(signingkey.upper()[-16:])
    ),
    None,
  )
  return {
    "gpg": gpg_available(),
    "keys": keys,
    "signingkey": signingkey,
    "format": fmt or "openpgp",
    "active": active["fingerprint"] if active else "",
    "git_name": git_name,
    "git_email": git_email,
    "github": {
      "checked": not gh_err,
      "count": len(gh_ids),
      "error": gh_err,
    },
  }


def generate_key(name: str, email: str) -> tuple[str, str]:
  """Create an ed25519 signing key. Returns (fingerprint, error)."""
  if not gpg_available():
    return "", "gpg is not installed in this container"
  if not name.strip() or not email.strip():
    return "", "a name and an email are required (they become the key's user id)"
  uid = f"{name.strip()} <{email.strip()}>"
  rc, _, err = run_cmd(
    [
      "gpg",
      "--batch",
      "--passphrase",
      "",
      "--quick-generate-key",
      uid,
      "ed25519",
      "sign",
      "0",
    ],
    timeout=120,
  )
  if rc != 0:
    return "", err or "gpg could not create a key"
  for key in secret_keys():
    if email.strip() in key["uid"]:
      return key["fingerprint"], ""
  return "", "key was created but could not be read back"


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #


class Job:
  """One CLI invocation, with its output kept for replay and follow-along."""

  def __init__(self, argv: list[str], cwd: str, repo: dict[str, Any]) -> None:
    self.id = uuid.uuid4().hex[:12]
    self.argv = argv
    self.cwd = cwd
    self.repo = {"id": repo["id"], "name": repo["name"]}
    self.started = time.time()
    self.finished: float | None = None
    self.exit: int | None = None
    self.cancelled = False
    self.lines: deque[tuple[float, str]] = deque(maxlen=MAX_LINES)
    self._proc: subprocess.Popen[str] | None = None
    self._cond = threading.Condition()

  def start(self) -> None:
    self._proc = subprocess.Popen(
      self.argv,
      cwd=self.cwd,
      stdin=subprocess.DEVNULL,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
      bufsize=1,
      env={**os.environ, "PYTHONUNBUFFERED": "1", "NO_COLOR": "1", "TERM": "dumb"},
    )
    threading.Thread(target=self._pump, daemon=True).start()

  def _pump(self) -> None:
    assert self._proc is not None and self._proc.stdout is not None
    for line in self._proc.stdout:
      with self._cond:
        self.lines.append((time.time(), line.rstrip("\n")))
        self._cond.notify_all()
    self._proc.wait()
    with self._cond:
      self.exit = self._proc.returncode
      self.finished = time.time()
      self._cond.notify_all()

  def cancel(self) -> bool:
    proc = self._proc
    if proc is None or proc.poll() is not None:
      return False
    self.cancelled = True
    proc.terminate()
    try:
      proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
      proc.kill()
    return True

  def snapshot(self, since: int = 0) -> dict[str, Any]:
    with self._cond:
      entries = list(self.lines)[since:]
      return {
        "id": self.id,
        "repo": self.repo,
        "argv": self.argv[2:],  # drop interpreter + script path
        "status": "running" if self.exit is None else "done",
        "exit": self.exit,
        "cancelled": self.cancelled,
        "started": self.started,
        "finished": self.finished,
        "elapsed": (self.finished or time.time()) - self.started,
        "next": since + len(entries),
        "lines": [{"t": t, "text": text} for t, text in entries],
      }

  def wait_for(self, since: int, timeout: float = 25.0) -> None:
    with self._cond:
      self._cond.wait_for(
        lambda: len(self.lines) > since or self.exit is not None, timeout=timeout
      )


JOBS: dict[str, Job] = {}
JOBS_LOCK = threading.Lock()


def new_job(argv: list[str], repo: dict[str, Any]) -> Job:
  job = Job(argv, repo["path"], repo)
  with JOBS_LOCK:
    JOBS[job.id] = job
  job.start()
  return job


# --------------------------------------------------------------------------- #
# Access - gh authentication, git credentials, and how git reaches GitHub
# --------------------------------------------------------------------------- #

AUTH_TTL = 20.0
AUTH_LOCK = threading.Lock()
AUTH_CACHE: dict[str, Any] = {"at": 0.0, "value": None}


def _gh_account() -> dict[str, Any]:
  """`gh auth status --json hosts`, with the text output as a fallback."""
  info: dict[str, Any] = {
    "installed": bool(shutil.which("gh")),
    "authenticated": False,
    "host": "github.com",
    "login": "",
    "scopes": "",
    "source": "",
    "error": "",
  }
  if not info["installed"]:
    info["error"] = "gh is not installed in this container"
    return info

  rc, out, _ = run_cmd(["gh", "auth", "status", "--json", "hosts"], timeout=20)
  if rc == 0 and out:
    try:
      hosts = (json.loads(out) or {}).get("hosts") or {}
      for host, entries in hosts.items():
        for entry in entries or []:
          if not entry.get("active"):
            continue
          info.update(
            host=host,
            authenticated=True,
            login=str(entry.get("login") or ""),
            scopes=str(entry.get("scopes") or ""),
            source=str(entry.get("tokenSource") or ""),
          )
          return info
      info["error"] = "gh has no active account"
      return info
    except (json.JSONDecodeError, AttributeError, TypeError):
      pass  # older gh, or something else answered - read the text form

  rc, out, err = run_cmd(["gh", "auth", "status"], timeout=20)
  text = f"{out}\n{err}"
  match = re.search(r"Logged in to (\S+) account (\S+)", text)
  if rc == 0 and match:
    info.update(
      host=match.group(1),
      authenticated=True,
      login=match.group(2),
    )
    scopes = re.search(r"Token scopes: (.+)", text)
    info["scopes"] = scopes.group(1).strip() if scopes else ""
    if "GH_TOKEN" in text or "GITHUB_TOKEN" in text:
      info["source"] = "environment"
    return info
  info["error"] = text.strip().splitlines()[-1] if text.strip() else "not signed in"
  return info


def _credential_helpers() -> list[str]:
  """gh writes a host-scoped helper, so ask for that one too."""
  out: list[str] = []
  for key in (
    "credential.helper",
    "credential.https://github.com.helper",
    "credential.http://github.com.helper",
  ):
    rc, value, _ = run_cmd(["git", "config", "--global", "--get-all", key])
    if rc == 0 and value:
      out.extend(line.strip() for line in value.splitlines() if line.strip())
  return out


def _ssh_keys() -> list[str]:
  home = Path(os.environ.get("HOME") or Path.home())
  out: list[str] = []
  for key in ("id_ed25519", "id_rsa", "id_ecdsa", "id_dsa"):
    path = home / ".ssh" / key
    if path.is_file():
      out.append(key)
  return out


def auth_report(force: bool = False) -> dict[str, Any]:
  """Everything the Access panel needs. Cached: `gh auth status` is not free."""
  with AUTH_LOCK:
    cached = AUTH_CACHE["value"]
    fresh = time.time() - AUTH_CACHE["at"] < AUTH_TTL
  if cached is not None and fresh and not force:
    return cached

  gh = _gh_account()
  helpers = _credential_helpers()
  report = {
    "gh": gh,
    "git": {
      "name": git("config", "--global", "user.name"),
      "email": git("config", "--global", "user.email"),
      "credential_helpers": helpers,
      "credentials_for_gh": any("gh" in h for h in helpers),
      "ssh_keys": _ssh_keys(),
    },
    "env": {
      "GH_TOKEN": bool(os.environ.get("GH_TOKEN")),
      "GITHUB_TOKEN": bool(os.environ.get("GITHUB_TOKEN")),
    },
    "host": gh["host"] or "github.com",
  }
  with AUTH_LOCK:
    AUTH_CACHE["at"] = time.time()
    AUTH_CACHE["value"] = report
  return report


def auth_invalidate() -> None:
  """Forget the auth answer - and every status that was computed under it."""
  with AUTH_LOCK:
    AUTH_CACHE["at"] = 0.0
    AUTH_CACHE["value"] = None
  STATUS.clear()


def gh_login_with_token(token: str) -> tuple[bool, str]:
  """Hand a PAT to gh over stdin, then wire git's credential helper."""
  token = token.strip()
  if not token:
    raise BadRequest("a token is required")
  if len(token) > 512 or any(ch.isspace() for ch in token):
    raise BadRequest("that does not look like a token")
  if not shutil.which("gh"):
    return False, "gh is not installed in this container"
  rc, out, err = run_cmd(
    ["gh", "auth", "login", "--with-token"], timeout=45, stdin_text=token + "\n"
  )
  if rc != 0:
    return False, err or out or "gh rejected the token"
  # a token does not configure git; without this an https push still fails
  run_cmd(["gh", "auth", "setup-git"], timeout=30)
  auth_invalidate()
  return True, ""


def gh_setup_git() -> tuple[bool, str]:
  if not shutil.which("gh"):
    return False, "gh is not installed in this container"
  rc, _out, err = run_cmd(["gh", "auth", "setup-git"], timeout=30)
  auth_invalidate()
  return rc == 0, "" if rc == 0 else err or "gh auth setup-git failed"


# --------------------------------------------------------------------------- #
# Request validation
# --------------------------------------------------------------------------- #


class BadRequest(Exception):
  pass


def build_argv(body: dict[str, Any], repo: dict[str, Any]) -> list[str]:
  """
  Turn a JSON body into an argv, from a whitelist.

  Nothing the browser sends is ever interpolated into a shell string. Each
  option becomes its own list element, and unknown keys are rejected loudly.
  `action: "clean"` is the one-click path: the full run with the defaults the
  dashboard promises. They are spelled out here so the argv preview can show
  them.
  """
  action = body.get("action", "run")
  if action == "clean":
    body = {**body, "action": "run", "one_click": True}
    action = "run"
  if action not in COMMANDS:
    raise BadRequest(f"unknown action {action!r}")

  argv = [sys.executable, str(TOOL), action]
  allowed = {
    "action",
    "paths",
    "dry_run",
    "keep_empty",
    "one_click",
    "branch",
    "divergence",
    "force",
    "skip_pr_check",
    "keep_branch",
    "timeout",
    "no_tags",
  }
  unknown = set(body) - allowed
  if unknown:
    raise BadRequest("unknown option(s): " + ", ".join(sorted(unknown)))

  if body.get("dry_run"):
    argv.append("--dry-run")
  for path in body.get("paths") or []:
    path = str(path).strip()
    if not path:
      continue
    if "\0" in path or path.startswith("-"):
      raise BadRequest(f"invalid path {path!r}")
    argv += ["--path", path]
  if body.get("keep_empty"):
    argv.append("--keep-empty")

  branch = str(body.get("branch") or "").strip()
  if branch:
    if branch.startswith("-") or "\0" in branch:
      raise BadRequest(f"invalid branch {branch!r}")
    # The page cleans a long-lived branch in place or lets the run find the
    # arena branch itself. It never aims -b at arena/*; the CLI still can.
    if branch.startswith(engine.ARENA_PREFIX):
      raise BadRequest(f"the page does not target {engine.ARENA_PREFIX}* branches")
    argv += ["--branch", branch]
  # One click never guesses what to do with diverged history. The engine
  # refuses without a terminal, and the UI then offers the two choices.
  divergence = body.get("divergence") or "ask"
  if divergence not in {"ask", "remote", "local"}:
    raise BadRequest(f"invalid divergence {divergence!r}")
  if divergence != "ask":
    argv += ["--on-divergence", divergence]
  if body.get("force"):
    argv.append("--force")
  if body.get("skip_pr_check"):
    argv.append("--skip-pr-check")
  if body.get("keep_branch"):
    argv.append("--keep-branch")
  if body.get("no_tags"):
    argv.append("--no-tags")
  timeout = body.get("timeout")
  if timeout not in (None, ""):
    try:
      minutes = int(timeout)
    except (TypeError, ValueError) as exc:
      raise BadRequest("timeout must be a whole number of minutes") from exc
    if minutes < 0:
      raise BadRequest("timeout cannot be negative")
    argv += ["--check-timeout", str(minutes * 60)]

  return argv


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

CONTENT_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".webp": "image/webp",
  ".woff2": "font/woff2",
  ".webmanifest": "application/manifest+json; charset=utf-8",
  ".ico": "image/x-icon",
  ".txt": "text/plain; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
  server_version = "arena-ui/" + VERSION
  reg: Registry
  verbose = False

  # -- plumbing ----------------------------------------------------------
  def log_message(self, fmt: str, *args: object) -> None:
    if self.verbose:
      sys.stderr.write(f"{self.address_string()} {fmt % args}\n")

  def _json(self, payload: Any, status: int = 200) -> None:
    raw = json.dumps(payload).encode()
    self.send_response(status)
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.send_header("Content-Length", str(len(raw)))
    self.send_header("Cache-Control", "no-store")
    self.end_headers()
    self.wfile.write(raw)

  def _error(self, message: str, status: int = 400) -> None:
    self._json({"error": message}, status)

  def _body(self) -> dict[str, Any]:
    try:
      length = int(self.headers.get("Content-Length") or 0)
    except ValueError as exc:
      raise BadRequest("bad Content-Length") from exc
    if length > 1_000_000:
      raise BadRequest("body too large")
    raw = self.rfile.read(length) if length else b"{}"
    try:
      parsed = json.loads(raw or b"{}")
    except json.JSONDecodeError as exc:
      raise BadRequest("body is not valid JSON") from exc
    if not isinstance(parsed, dict):
      raise BadRequest("body must be a JSON object")
    return parsed

  def _static(self, path: str) -> None:
    rel = "index.html" if path in ("/", "") else path.lstrip("/")
    target = (STATIC / rel).resolve()
    if STATIC.resolve() not in target.parents and target != STATIC.resolve():
      self._error("not found", 404)
      return
    if not target.is_file():
      self._error("not found", 404)
      return
    data = target.read_bytes()
    self.send_response(200)
    self.send_header(
      "Content-Type", CONTENT_TYPES.get(target.suffix, "application/octet-stream")
    )
    self.send_header("Content-Length", str(len(data)))
    # the worker has to be revalidated on every load. Otherwise a new version
    # of the app can never take over from the old cached shell
    no_store = target.suffix == ".html" or target.name == "sw.js"
    self.send_header(
      "Cache-Control", "no-store" if no_store else "public, max-age=86400"
    )
    if target.name == "sw.js":
      self.send_header("Service-Worker-Allowed", "/")
    self.end_headers()
    self.wfile.write(data)

  def _repo(self, repo_id_: str) -> dict[str, Any]:
    repo = self.reg.get(repo_id_)
    if not repo:
      raise KeyError(repo_id_)
    return repo

  # -- GET ---------------------------------------------------------------
  def do_GET(self) -> None:
    path = self.path.split("?", 1)[0]
    parts = [p for p in path.split("/") if p]
    try:
      if path == "/api/env":
        self._json(
          {
            "version": VERSION,
            "tool": tool_version(),
            "python": sys.version.split()[0],
            "arch": os.uname().machine if hasattr(os, "uname") else "?",
            "tools": {
              "git": bool(shutil.which("git")),
              "gh": bool(shutil.which("gh")) and auth_report()["gh"]["authenticated"],
              "git-filter-repo": bool(shutil.which("git-filter-repo")),
              "gpg": gpg_available(),
            },
            "data": str(self.reg.data),
          }
        )
      elif path == "/api/repos":
        repos = self.reg.all()
        with ThreadPoolExecutor(max_workers=4) as pool:
          statuses = list(pool.map(lambda r: STATUS.get(r), repos))
        payload = []
        for repo, status in zip(repos, statuses):
          payload.append({**repo, "status": status})
        self._json(payload)
      elif len(parts) == 3 and parts[:2] == ["api", "repos"]:
        repo = self._repo(parts[2])
        self._json({**repo, "status": STATUS.get(repo)})
      elif len(parts) == 4 and parts[:2] == ["api", "repos"] and parts[3] == "commits":
        repo = self._repo(parts[2])
        query = urllib.parse.parse_qs(
          self.path.split("?", 1)[1] if "?" in self.path else ""
        )
        try:
          limit = max(1, min(100, int(query.get("limit", ["30"])[0])))
        except ValueError:
          limit = 30
        self._json(commits_report(repo, limit))
      elif len(parts) == 4 and parts[:2] == ["api", "repos"] and parts[3] == "tree":
        repo = self._repo(parts[2])
        query = urllib.parse.parse_qs(
          self.path.split("?", 1)[1] if "?" in self.path else ""
        )
        tree = tree_report(repo, query.get("path", [""])[0])
        if tree is None:
          self._error("no such directory", 404)
        else:
          self._json(tree)
      elif path == "/api/auth":
        self._json(auth_report())
      elif path == "/healthz":
        # Deliberately cheap. docker's HEALTHCHECK and a Tailscale monitor both
        # poll this on a short interval. It must not shell out to git.
        self._json(
          {
            "ok": True,
            "version": VERSION,
            "uptime": round(time.time() - STARTED, 1),
            "repos": len(self.reg.all()),
          }
        )
      elif path == "/api/signing":
        self._json(signing_report())
      elif path == "/api/settings":
        self._json(settings_report())
      elif len(parts) == 3 and parts[0] == "api" and parts[1] == "jobs":
        job = JOBS.get(parts[2])
        if not job:
          self._error("no such job", 404)
        else:
          since = int(self.headers.get("Last-Event-Id") or 0)
          self._json(job.snapshot(since))
      elif len(parts) == 4 and parts[0] == "api" and parts[1] == "jobs":
        job = JOBS.get(parts[2])
        if not job or parts[3] != "events":
          self._error("no such job", 404)
        else:
          self._stream(job)
      else:
        self._static(path)
    except KeyError:
      self._error("no such repo", 404)
    except ValueError:
      self._error("bad request", 400)
    except BrokenPipeError:
      pass
    except Exception as exc:
      self._error(f"internal error: {exc}", 500)

  # -- POST --------------------------------------------------------------
  def do_POST(self) -> None:
    path = self.path.split("?", 1)[0]
    parts = [p for p in path.split("/") if p]
    try:
      if path == "/api/repos":
        body = self._body()
        source = normalize_source(str(body.get("source") or ""))
        if not source:
          raise BadRequest("paste a repo URL or a path to a work tree")
        if URL_RE.match(source):
          entry, err = clone_url(source, self.reg)
        else:
          entry, err = register_path(source, self.reg)
        if not entry:
          self._error(err or "could not add that repo", 400)
        else:
          self._json({**entry, "status": STATUS.get(entry)}, 201)
      elif len(parts) == 4 and parts[:2] == ["api", "repos"] and parts[3] == "reset":
        repo = self._repo(parts[2])
        target = reset_to_origin(repo)
        STATUS.drop(repo["id"])
        self._json({"reset": target, "status": STATUS.get(repo)})
      elif len(parts) == 4 and parts[:2] == ["api", "repos"] and parts[3] == "remove":
        repo = self.reg.remove(parts[2])
        if not repo:
          self._error("no such repo", 404)
          return
        STATUS.drop(parts[2])
        body = self._body()
        if (
          body.get("delete")
          and repo.get("managed")
          and repo["path"].startswith(str(self.reg.clones))
        ):
          shutil.rmtree(repo["path"], ignore_errors=True)
        self._json({"removed": repo["id"]})
      elif len(parts) == 4 and parts[:2] == ["api", "repos"] and parts[3] == "jobs":
        repo = self._repo(parts[2])
        body = self._body()
        argv = build_argv(body, repo)
        job = new_job(argv, repo)
        STATUS.drop(repo["id"])
        self._json({"id": job.id, "argv": argv[2:]}, 201)
      elif path == "/api/auth":
        self._handle_auth(self._body())
      elif path == "/api/signing":
        self._handle_signing(self._body())
      elif path == "/api/settings":
        self._handle_settings(self._body())
      elif (
        len(parts) == 4
        and parts[0] == "api"
        and parts[1] == "jobs"
        and parts[3] == "cancel"
      ):
        job = JOBS.get(parts[2])
        if not job:
          self._error("no such job", 404)
        else:
          self._json({"cancelled": job.cancel()})
      else:
        self._error("not found", 404)
    except BadRequest as exc:
      self._error(str(exc), 400)
    except KeyError:
      self._error("no such repo", 404)
    except BrokenPipeError:
      pass
    except Exception as exc:
      self._error(f"internal error: {exc}", 500)

  def _handle_auth(self, body: dict[str, Any]) -> None:
    action = body.get("action", "check")
    if action == "check":
      before = auth_report()["gh"]
      report = auth_report(force=True)
      after = report["gh"]
      if (before["authenticated"], before["login"]) != (
        after["authenticated"],
        after["login"],
      ):
        STATUS.clear()
      self._json(report)
    elif action == "token":
      ok, err = gh_login_with_token(str(body.get("token") or ""))
      if not ok:
        self._error(err, 400)
      else:
        self._json(auth_report(force=True))
    elif action == "setup_git":
      ok, err = gh_setup_git()
      if not ok:
        self._error(err, 400)
      else:
        self._json(auth_report(force=True))
    else:
      raise BadRequest("unknown auth action")

  def _handle_settings(self, body: dict[str, Any]) -> None:
    action = body.get("action")
    if action == "identity":
      name = str(body.get("name") or "").strip()
      email = str(body.get("email") or "").strip()
      if not name or not email:
        raise BadRequest("name and email are required")
      if "@" not in email or any(c.isspace() for c in email):
        raise BadRequest("that is not an email address")
      for key, value in (("user.name", name), ("user.email", email)):
        rc, _, err = run_cmd(["git", "config", "--global", key, value])
        if rc != 0:
          raise BadRequest(err or f"could not set {key}")
    elif action == "claims":
      set_global_config_all(
        "arena.claim-email", clean_values(body.get("emails"), "emails")
      )
      set_global_config_all(
        "arena.claim-name", clean_values(body.get("names"), "names")
      )
    else:
      raise BadRequest("unknown action")
    self._json(settings_report())

  def _handle_signing(self, body: dict[str, Any]) -> None:
    action = body.get("action")
    if action == "create":
      fingerprint, err = generate_key(
        str(body.get("name") or ""), str(body.get("email") or "")
      )
      if err:
        self._error(err, 400)
        return
      git("config", "--global", "user.signingkey", fingerprint)
      git("config", "--global", "gpg.format", "openpgp")
      rc, pub, err2 = run_cmd(["gpg", "--armor", "--export", fingerprint])
      self._json(
        {
          "fingerprint": fingerprint,
          "public_key": pub if rc == 0 else "",
          "error": err2,
        },
        201,
      )
    elif action == "use":
      fingerprint = str(body.get("fingerprint") or "").strip()
      if not fingerprint:
        raise BadRequest("fingerprint is required")
      git("config", "--global", "user.signingkey", fingerprint)
      git("config", "--global", "gpg.format", "openpgp")
      self._json(signing_report())
    elif action == "recheck":
      self._json(signing_report())
    elif action == "public_key":
      fingerprint = str(body.get("fingerprint") or "").strip()
      rc, pub, err = run_cmd(["gpg", "--armor", "--export", fingerprint])
      self._json({"public_key": pub if rc == 0 else "", "error": err})
    else:
      raise BadRequest("unknown signing action")

  # -- server-sent events ------------------------------------------------
  def _stream(self, job: Job) -> None:
    since = int(self.headers.get("Last-Event-Id") or 0)
    self.send_response(200)
    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
    self.send_header("Cache-Control", "no-store")
    self.send_header("X-Accel-Buffering", "no")
    self.end_headers()

    while True:
      job.wait_for(since)
      snap = job.snapshot(since)
      since = snap["next"]
      try:
        self.wfile.write(f"id: {since}\ndata: {json.dumps(snap)}\n\n".encode())
        self.wfile.flush()
      except (BrokenPipeError, ConnectionResetError):
        return
      if snap["status"] == "done" and not snap["lines"]:
        return


def main() -> int:
  parser = argparse.ArgumentParser(
    prog="arena-ui", description="Web UI for arena-cleanup."
  )
  parser.add_argument(
    "--data",
    default=os.environ.get(
      "ARENA_DATA", str(Path.home() / ".local/share/arena-cleanup")
    ),
    help="where the repo list and clones live",
  )
  parser.add_argument("--host", default=os.environ.get("ARENA_HOST", "0.0.0.0"))
  parser.add_argument(
    "--port", type=int, default=int(os.environ.get("ARENA_PORT", "8080"))
  )
  parser.add_argument("-v", "--verbose", action="store_true", help="log every request")
  args = parser.parse_args()

  if not TOOL.is_file():
    print(f"arena-ui: {TOOL} not found - the UI sits next to the tool", file=sys.stderr)
    return 2

  reg = Registry(Path(args.data).expanduser())
  Handler.reg = reg
  Handler.verbose = args.verbose

  httpd = ThreadingHTTPServer((args.host, args.port), Handler)
  httpd.daemon_threads = True
  print(
    f"arena-ui {VERSION} on http://{args.host}:{args.port}  data={reg.data}",
    flush=True,
  )
  try:
    httpd.serve_forever()
  except KeyboardInterrupt:
    print("\nbye", flush=True)
  finally:
    httpd.server_close()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
