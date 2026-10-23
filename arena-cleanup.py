#!/usr/bin/env python3
"""
arena-cleanup - Arena branch cleanup + history rewrite in one file.

One file, standard library only. It runs from a terminal inside any clone.
The web UI spawns the same file as a subprocess, one process per run:

    arena-cleanup run     full flow: cleanup -> PR gate -> rewrite -> push.
    arena-cleanup strip   just the history rewrite.
    arena-cleanup doctor  verify environment / config.

On a PC: copy this file and arena-cleanup.cmd somewhere on PATH. It needs
Python 3.11 or newer, git, and a signed-in gh. --path needs git-filter-repo,
signing needs gpg.

The argument surface below is also the contract with ui/server.py.
ui/server.py::build_argv is the only code that constructs it.

Flags: -n dry run, -v verbose, -b/--branch, -d/--delete-branch,
-k/--skip-pr-check, -t/--check-timeout, -i/--check-interval, -c/--check (strip),
-p/--path (run, strip), -T/--no-tags (run).

Everything else is a per-machine setting, not a per-run choice. The identity
is `git config user.name` and `user.email`. The claim rules are the global git
config keys `arena.claim-email` and `arena.claim-name`, else the constants at
the top of this file. Signing and the arena prefix are constants.

Exit codes: 0 ok / 1 error / 2 usage / 7 strip -c: rewrite needed
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

# the one version of this file. pyproject.toml carries the same number for the
# web app, and tests/test_cli.py keeps the two equal.
__version__ = "0.3.0"
PROG = "arena-cleanup"

# ==== Defaults: edit these, or override per run with the matching flags ======

# The claim rules. `git config --global --add arena.claim-email <email>` and
# `--add arena.claim-name <name>` replace them, each constant applies while its key is unset.

# Emails that were yours (space separated). The configured user.email is
# always claimed too.
CLAIM_EMAILS = "60245796+nemoe7@users.noreply.github.com"

# Commits authored/committed by these names get claimed and rewritten
# (space separated, matched against both author and committer name).
CLAIM_NAMES = "arena-ai-coding-agent[bot] arena-agent arena"

# The cleanup scans only branches under this prefix.
ARENA_PREFIX = "arena/"

# GPG-sign the commits this tool claims (the old strip-history always did this).
# Set to False if you have no signing key configured.
SIGN_COMMITS = True

# ==== Output =================================================================

RESET = "\x1b[0m"
DIM = "\x1b[90m"
# INFO cyan, OK green, WARN yellow, ERROR red.
LEVEL_COLOR = {
  "INFO": "\x1b[96m",
  "OK": "\x1b[92m",
  "WARN": "\x1b[93m",
  "ERROR": "\x1b[91m",
}

# Check states, in the vocabulary GitHub uses across CheckRun and StatusContext.
OK_STATES = {"SUCCESS", "NEUTRAL", "SKIPPED"}
PENDING_STATES = {
  "",
  "PENDING",
  "QUEUED",
  "IN_PROGRESS",
  "WAITING",
  "EXPECTED",
  "REQUESTED",
}
FAIL_STATES = {
  "FAILURE",
  "ERROR",
  "TIMED_OUT",
  "ACTION_REQUIRED",
  "STARTUP_FAILURE",
  "CANCELLED",
  "CANCELED",
  "STALE",
}

# kept for the docstring/help wording
BAD_CONCLUSIONS = FAIL_STATES
PENDING_CONCLUSIONS = PENDING_STATES


def _enable_windows_ansi() -> None:
  """Enable VT sequences for classic conhost (Win10+). No-op elsewhere."""
  if os.name != "nt":
    return
  try:
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-11)
    mode = ctypes.c_uint32()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
      kernel32.SetConsoleMode(handle, mode.value | 0x0004)
  except Exception:
    pass


class Log:
  """One formatting rule for every line: <ISO timestamp> LEVEL message."""

  def __init__(self, verbose: bool = False) -> None:
    self.verbose = verbose
    self._status = ""
    self.tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
    # The environment variable NO_COLOR turns colour off. There is no flag for it
    self.color = os.environ.get("NO_COLOR") is None and (
      self.tty or bool(os.environ.get("FORCE_COLOR"))
    )

  # -- internals ----------------------------------------------------------
  @staticmethod
  def _stamp() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")

  def status(self, text: str) -> None:
    """
    Draw a transient status line that overwrites itself (terminal only).

    Keeps a long scan from scrolling hundreds of progress lines past the
    user while still showing that something is happening.
    """
    if not self.tty:
      return
    padding = " " * max(0, len(self._status) - len(text))
    self._status = text
    sys.stdout.write("\r" + text + padding)
    sys.stdout.flush()

  def clear_status(self) -> None:
    if not self.tty or not self._status:
      return
    sys.stdout.write("\r" + " " * len(self._status) + "\r")
    sys.stdout.flush()
    self._status = ""

  def _print(self, text: str) -> None:
    if self._status:  # never print on top of the status line
      self.clear_status()
    try:
      print(text, flush=True)
    except UnicodeEncodeError:
      print(text.encode("ascii", "replace").decode("ascii"), flush=True)

  def _write(self, level: str, msg: str) -> None:
    stamp = self._stamp()
    tag = f"{LEVEL_COLOR[level]}{level:<5}{RESET}" if self.color else f"{level:<5}"
    self._print(f"{stamp} {tag} {msg}")

  # -- public -------------------------------------------------------------
  def info(self, msg: str) -> None:
    self._write("INFO", msg)

  def ok(self, msg: str) -> None:
    self._write("OK", msg)

  def warning(self, msg: str) -> None:
    self._write("WARN", msg)

  def error(self, msg: str) -> None:
    self._write("ERROR", msg)

  def dim(self, msg: str) -> None:
    self._print(f"{DIM}{msg}{RESET}" if self.color else msg)

  def plain(self, text: str = "") -> None:
    """A line with no timestamp - for interactive question text only."""
    self._print(text)

  def block(self, text: str, prefix: str = "  | ") -> None:
    """Verbatim (untimestamped) dump of command output, indented."""
    for line in text.splitlines():
      self._print((f"{DIM}{prefix + line}{RESET}") if self.color else prefix + line)


# ==== Subprocess plumbing ====================================================


class Fail(Exception):
  """User-facing failure: already has a human-readable message."""


class ToolError(Exception):
  """A git/gh invocation failed. Carries the captured output for dumping."""

  def __init__(
    self, argv: Sequence[str], rc: int, out: bytes, err: bytes, context: str = ""
  ) -> None:
    self.argv = list(argv)
    self.rc = rc
    self.out = _decode(out)
    self.err = _decode(err)
    self.streamed = not out and not err
    pretty = " ".join(shlex.quote(a) for a in self.argv)
    message = f"command failed (exit {rc}): {pretty}"
    super().__init__(f"{context}: {message}" if context else message)


def _decode(raw: bytes) -> str:
  return raw.decode("utf-8", "replace").strip()


class Result:
  __slots__ = ("argv", "err", "out", "rc")

  def __init__(self, argv: Sequence[str], rc: int, out: bytes, err: bytes) -> None:
    self.argv, self.rc, self.out, self.err = list(argv), rc, out, err

  @property
  def text(self) -> str:
    return _decode(self.out)

  @property
  def errtext(self) -> str:
    return _decode(self.err)

  def lines(self) -> list[str]:
    return [ln for ln in self.text.splitlines() if ln.strip()]


_log: Log | None = None  # set in main(), used by run() for verbose streaming


def run(
  argv: Sequence[str],
  *,
  check: bool = True,
  stdin: bytes | None = None,
  env: dict[str, str] | None = None,
) -> Result:
  """
  Run a command.

  Quiet by default: it captures stdout/stderr and shows them only if the command
  fails. With --verbose it echoes the same output afterwards, after the
  command echo line. Capture always happens, because plenty of callers parse
  the output. A "stream live" mode that loses it broke every one of them.
  """
  argv = [str(a) for a in argv]
  verbose = _log is not None and _log.verbose
  if verbose:
    _log.dim("$ " + " ".join(shlex.quote(a) for a in argv))
  proc = subprocess.run(argv, input=stdin, capture_output=True, env=env, check=False)
  res = Result(argv, proc.returncode, proc.stdout or b"", proc.stderr or b"")
  if verbose:
    for stream in (res.out, res.err):
      text = stream.decode("utf-8", "replace").rstrip()
      if text:
        _log.block(text)
  if check and res.rc != 0:
    raise ToolError(argv, res.rc, res.out, res.err)
  return res


def git(*args: object, **kw) -> Result:
  return run(["git", *args], **kw)


def gh(*args: object, **kw) -> Result:
  return run(["gh", *args], **kw)


def which(tool: str) -> str | None:
  from shutil import which as _which

  return _which(tool)


# ==== Settings ===============================================================


class Settings:
  """
  There are no flags for identity, claim rules, or signing, by design. They
  are per-machine settings, not per-run choices. The claim rules come from the
  global git config, else from the constants at the top of this file. Flip
  SIGN_COMMITS there to stop signing commits.
  """

  def __init__(self, args: argparse.Namespace) -> None:
    self.claim_emails = claim_rules("arena.claim-email") or _split(CLAIM_EMAILS)
    self.claim_names = claim_rules("arena.claim-name") or _split(CLAIM_NAMES)
    self.sign = SIGN_COMMITS
    self.paths = list(getattr(args, "paths", None) or [])
    self.no_tags = bool(getattr(args, "no_tags", False))
    self.dry_run = bool(args.dry_run)
    self.on_divergence = getattr(args, "on_divergence", "ask")
    self.verbose = bool(args.verbose)

  def describe(self) -> str:
    return "claimed emails={}; claimed names={}; sign={}".format(
      ", ".join(self.claim_emails) or "-",
      ", ".join(self.claim_names) or "-",
      "yes" if self.sign else "no",
    )


def _split(value: str) -> list[str]:
  return [p for p in value.replace(",", " ").split() if p]


def claim_rules(key: str) -> list[str]:
  """Every value of a multi-valued global git config key, in order."""
  text = git("config", "--global", "--get-all", key, check=False).text
  return [line.strip() for line in text.splitlines() if line.strip()]


# ==== Git and gh queries =====================================================


def require_repo() -> None:
  """Fail early, and with a clear message, when there is no repo to work on."""
  if which("git") is None:
    return  # require_tools() reports this better
  if git("rev-parse", "--is-inside-work-tree", check=False).text != "true":
    raise Fail("not inside a git repo (run me from one)")
  bare = git("rev-parse", "--is-bare-repository", check=False).text  # nonemo: NMO002
  if bare == "true":
    raise Fail("this is a bare repo, run me from a working tree")


def require_tools(log: Log, *, gh_required: bool = False) -> None:
  """git is always needed. Only the full `run` flow needs the GitHub CLI."""
  needed = ["git"] + (["gh"] if gh_required else [])
  missing = [t for t in needed if not which(t)]
  if missing:
    raise Fail(
      "missing required tool(s): {}{}".format(
        ", ".join(missing),
        "  (install GitHub CLI: https://cli.github.com/)" if "gh" in missing else "",
      )
    )


def default_branch(log: Log) -> str:
  res = git("ls-remote", "--symref", "origin", "HEAD", check=False)
  for line in res.lines():
    parts = line.split()
    if len(parts) >= 2 and parts[0] == "ref:" and parts[1].startswith("refs/heads/"):
      return parts[1][len("refs/heads/") :]
  if res.errtext:
    log.block(res.errtext)  # git's own explanation, verbatim
  raise Fail(
    "cannot determine the origin default branch "
    "(is the 'origin' remote configured and reachable?)"
  )


def current_branch() -> str:
  return git("branch", "--show-current", check=False).text


def head_short(rev: str = "HEAD") -> str:
  return git("rev-parse", "--short", rev, check=False).text or "?"


def local_arena_branches() -> list[str]:
  res = git("for-each-ref", "--format=%(refname:short)", f"refs/heads/{ARENA_PREFIX}")
  return res.lines()


def remote_arena_branches() -> list[str]:
  res = git(
    "for-each-ref", "--format=%(refname:short)", f"refs/remotes/origin/{ARENA_PREFIX}"
  )
  return res.lines()


# ==== Step 1: drop local arena/* branches that no longer exist on origin =====


def drop_stale_local_branches(log: Log, current: str, dry_run: bool) -> int:
  log.info(f"scanning local {ARENA_PREFIX}* branches")
  removed = 0
  for branch in local_arena_branches():
    if (
      git(
        "show-ref",
        "--verify",
        "--quiet",
        f"refs/remotes/origin/{branch}",
        check=False,
      ).rc
      == 0
    ):
      log.info(f"keeping {branch} (still on origin)")
      continue
    if branch.lower() == current.lower():
      log.info(f"keeping {branch} (currently checked out)")
      continue
    if dry_run:
      log.warning(f"would delete stale local branch {branch}")
      removed += 1
      continue
    log.warning(f"deleting stale local branch {branch}")
    res = git("branch", "-D", branch, check=False)
    if res.rc != 0:
      raise ToolError(res.argv, res.rc, res.out, res.err)
    removed += 1
  if not removed:
    log.info(f"no stale local {ARENA_PREFIX}* branches")
  return removed


# ==== Step 2: land on the arena branch =======================================

# Interactive prompts, used only where a guess would destroy work. They choose the arena
# branch among several, confirm a diverged local branch, and a push that drops commits.


def _interactive() -> bool:
  """Can we actually ask a human? (a terminal on both ends, and not piped)"""
  try:
    return sys.stdin.isatty() and sys.stdout.isatty()
  except Exception:
    return False


def ask_choice(
  log: Log,
  question: str,
  options: Sequence[tuple[str, str]],
  default: str | None = None,
) -> str | None:
  """
  Ask the user to select one of `options` = [(key, description), ...].

  Returns the chosen key, or None when they cancel. No terminal to ask on also
  counts as a cancel, because that is the only safe answer.
  """
  if not _interactive():
    log.warning(
      "no terminal to ask on. Not guessing (use the flags shown below "
      "to decide this non-interactively)"
    )
    return default if default is not None else None

  while True:
    log.plain("")
    log.plain(question)
    for index, (key, description) in enumerate(options, 1):
      log.plain(f"  {index}) {description}")
    log.plain("")
    try:
      answer = input(f"choose 1-{len(options)} [c to cancel]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
      log.plain("")
      return None
    if answer in ("c", "cancel", "q", "quit", ""):
      return None
    if answer.isdigit() and 1 <= int(answer) <= len(options):
      return options[int(answer) - 1][0]
    # also accept the key itself, e.g. a branch name
    for key, _ in options:
      if answer == key.lower():
        return key
    log.plain(f"  (did not understand {answer!r})")


def confirm(log: Log, question: str, *, default: bool = False) -> bool:
  """Yes/no question. Without a terminal, returns `default` and says so."""
  if not _interactive():
    log.warning("no terminal to ask on, assuming %s" % ("yes" if default else "no"))
    return default
  suffix = " [Y/n] " if default else " [y/N] "
  while True:
    try:
      answer = input(question + suffix).strip().lower()
    except (EOFError, KeyboardInterrupt):
      log.plain("")
      return default
    if answer in ("y", "yes"):
      return True
    if answer in ("n", "no", ""):
      return False
    log.plain("  (please answer y or n)")


def select_arena_branch(log: Log, wanted: str = "") -> tuple[str, str]:
  """
  Choose the arena branch to work on: (local name, remote-tracking ref).

  Several origin/arena/* branches usually means leftover sessions. Nothing is
  guessed: the tool lists them, and the user selects. Without a terminal (and so
  without an answer) the run stops rather than touching the wrong branch.
  `-a <branch>` answers the menu without a prompt.
  """
  remotes = remote_arena_branches()
  if not remotes:
    raise Fail(f"no origin/{ARENA_PREFIX}* branch found")
  if wanted:
    remote_ref = wanted if wanted.startswith("origin/") else f"origin/{wanted}"
    if remote_ref not in remotes:
      raise Fail(f"{remote_ref} is not an origin/{ARENA_PREFIX}* branch")
  elif len(remotes) == 1:
    remote_ref = remotes[0]
  else:
    log.warning(f"{len(remotes)} origin/{ARENA_PREFIX}* branches found")
    choice = ask_choice(
      log,
      "Which one should this run clean? (the others are left alone)",
      [(r, f"{r}   (tip: {head_short(r)})") for r in remotes],
    )
    if choice is None:
      raise Fail(
        f"cancelled: {len(remotes)} origin/{ARENA_PREFIX}* branches found and "
        "none chosen (pass -a <branch> to choose without a prompt)"
      )
    remote_ref = choice
  return remote_ref[len("origin/") :], remote_ref


def branch_exists(ref: str) -> bool:
  return git("show-ref", "--verify", "--quiet", ref, check=False).rc == 0


def ensure_branch(
  log: Log,
  name: str,
  *,
  dry_run: bool,
  remote_ref: str = "",
  set_upstream: bool = False,
) -> str:
  """
  Make sure `name` is the checked-out branch, creating a tracking branch when
  it only exists on origin. Returns the rev to work against: HEAD normally, or
  a read-only ref in a dry run. A dry run never touches the working tree.
  """
  remote_ref = remote_ref or f"origin/{name}"
  if current_branch().lower() == name.lower():
    return name if dry_run else "HEAD"

  if branch_exists(f"refs/heads/{name}"):
    if dry_run:
      log.info(f"would switch to {name}")
      return name
    log.info(f"switching to {name}")
    res = git("switch", name, check=False)
    if res.rc != 0:
      raise ToolError(
        res.argv, res.rc, res.out, res.err, context=f"failed to switch to {name}"
      )
    if set_upstream and branch_exists(f"refs/remotes/{remote_ref}"):
      res = git("branch", f"--set-upstream-to={remote_ref}", name, check=False)
      if res.rc != 0:
        raise ToolError(
          res.argv,
          res.rc,
          res.out,
          res.err,
          context=f"failed to set upstream of {name} to {remote_ref}",
        )
    log.ok(f"switched to {name}")
    return "HEAD"

  if not branch_exists(f"refs/remotes/{remote_ref}"):
    raise Fail(f"branch not found: {name} (not local, and no {remote_ref})")

  if dry_run:
    log.info(f"would switch to {name} (tracking {remote_ref})")
    return remote_ref

  log.info(f"switching to {name} (tracking {remote_ref})")
  res = git("switch", "--track", remote_ref, check=False)
  if res.rc != 0:
    raise ToolError(
      res.argv, res.rc, res.out, res.err, context=f"failed to switch to {name}"
    )
  if set_upstream:
    res = git("branch", f"--set-upstream-to={remote_ref}", name, check=False)
    if res.rc != 0:
      raise ToolError(
        res.argv,
        res.rc,
        res.out,
        res.err,
        context=f"failed to set upstream of {name} to {remote_ref}",
      )
  log.ok(f"switched to {name}")
  return "HEAD"


def require_upstream() -> None:
  if (
    git(
      "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", check=False
    ).rc
    != 0
  ):
    raise Fail("current branch has no upstream configured")


def upstream_ref() -> str:
  """e.g. 'origin/arena/session-xyz', or '' when the branch has no upstream."""
  return git(
    "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", check=False
  ).text


def rev_count(spec: str) -> int:
  text = git("rev-list", "--count", spec, check=False).text
  return int(text) if text.isdigit() else 0


def pull_latest(log: Log, cfg: Settings, default: str) -> bool:
  """
  Reconcile the local branch with its upstream. Returns False if the user
  chose to cancel.

  Fast-forward only, on purpose: origin/arena/* keeps whatever the session
  first pushed, so after a local rewrite the two have diverged. A plain
  `git pull` would paper over that with a merge commit. That commit then ends
  up in the history pushed to the default branch.

  Three outcomes when the branches have diverged:

    * identical content, different commit ids -> the expected rewrite case.
      Local history wins, no question asked.

    * local simply ahead -> local wins, no question asked.

    * different content *and* commits on both sides -> we cannot guess which
      side matters. We stop and ask whether to replace the local branch with
      its remote copy. Cancelling aborts the whole run.
  """
  if cfg.dry_run:
    log.info("would pull latest changes (fast-forward only)")
    return True

  upstream = upstream_ref()
  if not upstream:
    log.info("no upstream configured for %s, skipping pull" % (current_branch() or "?"))
    return True

  if not rev_count(f"{upstream}..HEAD"):
    log.info("pulling latest changes (fast-forward only)")
    before = head_short()
    git("pull", "--ff-only")
    after = head_short()
    log.ok(
      f"pulled ({before} -> {after})"
      if before != after
      else f"already up to date ({after})"
    )
    return True

  upstream_only = rev_count(f"HEAD..{upstream}")
  same_content = (
    same_content_as(default, "HEAD")
    and git("diff", "--quiet", upstream, "HEAD", "--", check=False).rc == 0
  )

  if same_content:
    log.info(
      f"local history is a rewritten version of {upstream} (same content, "
      "new commit ids), keeping local history"
    )
    return True
  if not upstream_only:
    log.info(f"local history is ahead of {upstream}, keeping local history")
    return True

  # ------------ diverged for real: different commits, different content ----
  log.warning(f"local {current_branch()} and {upstream} have diverged")
  log.warning(
    f"  {upstream_only} commit(s) only on {upstream}, "
    f"{rev_count(f'{upstream}..HEAD')} commit(s) only here"
  )
  log.dim(f"    only on {upstream}: git log --oneline HEAD..{upstream}")
  log.dim(f"    only here:   git log --oneline {upstream}..HEAD")

  if cfg.on_divergence == "local":
    log.info("--on-divergence=local: keeping local history")
    return True
  if cfg.on_divergence == "ask":
    choice = ask_choice(
      log,
      "The local branch and its remote copy have different commits AND "
      f"different content.\nReplace local history with {upstream}?",
      [
        ("remote", f"overwrite local with {upstream} (local commits are discarded)"),
        ("local", "keep local history (remote commits are left as they are)"),
      ],
    )
    if choice is None:
      log.warning("cancelled: local and remote differ, local history kept")
      return False
    if choice == "local":
      log.info("keeping local history")
      return True

  # either --on-divergence=remote, or the user selected it
  log.warning(f"replacing local {current_branch()} with {upstream}")
  res = git("reset", "--hard", upstream, check=False)
  if res.rc != 0:
    raise ToolError(
      res.argv,
      res.rc,
      res.out,
      res.err,
      context=f"could not reset {current_branch()} to {upstream}",
    )
  log.ok(f"local history is now {upstream} ({head_short()})")
  return True


def force_push(
  log: Log,
  default: str,
  dry_run: bool,
  rev: str = "HEAD",
  force: bool = False,
  ignore: set[str] | None = None,
) -> None:
  """
  Publish HEAD onto origin/<default>.

  Without `force` the push spells the lease out, as
  `--force-with-lease=refs/heads/<default>:<sha>` with the value fetched at the
  start of the run. The guard is pinned to the one ref we overwrite. Nothing
  moves under us between the fetch and the push. With `force` the push is a
  plain `git push --force`, which lands even when origin/<default> moved.
  """
  remote_ref = f"refs/heads/{default}"
  expected = git("rev-parse", f"origin/{default}", check=False).text
  verb = "force-push (no lease)" if force else "push (with lease)"

  if dry_run:
    log.info(f"would {verb} {rev} ({head_short(rev)}) -> origin/{default}")
    at_risk = at_risk_on_origin(default, rev, ignore)
    if at_risk:
      outcome = "publish anyway (-f)" if force else "stop here"
      log.warning(
        f"a real run would {outcome}: {len(at_risk)} commit(s) on "
        f"origin/{default} are not part of this push and would be dropped"
      )
      for line in at_risk[:10]:
        log.dim("    " + line)
    return

  at_risk = at_risk_on_origin(default, rev, ignore)
  if at_risk:
    log.warning(
      f"this push replaces origin/{default}, and {len(at_risk)} commit(s) "
      "there are not part of what is being published:"
    )
    for line in at_risk[:10]:
      log.dim("    " + line)
    if len(at_risk) > 10:
      log.dim(f"    ... and {len(at_risk) - 10} more")
    if force:
      log.warning("--force set, publishing anyway")
    elif confirm(log, "Publish anyway? Those commit(s) will be dropped"):
      log.warning("confirmed, publishing anyway")
    else:
      raise Fail(
        f"cancelled before pushing: origin/{default} has {len(at_risk)} "
        "commit(s) that this push would drop (pass -f to publish anyway)"
      )

  if force:
    guard = "--force"
  elif expected:
    guard = f"--force-with-lease={remote_ref}:{expected}"
  else:  # empty remote: nothing to protect
    guard = "--force-with-lease"
  doing = "force-pushing (no lease)" if force else "pushing (with lease)"
  log.info(f"{doing} HEAD -> {remote_ref}")
  git("push", guard, "origin", f"HEAD:{default}")
  log.ok(f"pushed {head_short()} to origin/{default}")


def already_published(default: str, rev: str = "HEAD") -> bool:
  """
  True when origin/<default> already contains HEAD, i.e. nothing to publish.

  History-based on purpose. The old batch used `git diff --quiet origin/main
  HEAD`, which compares *trees*. It reports "already in sync" whenever the
  content matches, even when HEAD's commits never reached origin.

  Commits rewritten locally sit on new hashes that origin has never seen.
  That silently skipped the push.
  """
  return (
    git("merge-base", "--is-ancestor", rev, f"origin/{default}", check=False).rc == 0
  )


# ==== Step 3: PR gate ========================================================


def find_open_pr(branch: str) -> int | None:
  res = gh(
    "pr",
    "list",
    "--head",
    branch,
    "--state",
    "open",
    "--json",
    "number",
    "--limit",
    "1",
    check=False,
  )
  if res.rc != 0:
    raise ToolError(res.argv, res.rc, res.out, res.err)
  try:
    items = json.loads(res.text or "[]")
  except ValueError:
    raise Fail("could not parse `gh pr list` output")
  return int(items[0]["number"]) if items else None


def _duration(seconds: float) -> str:
  seconds = int(seconds)
  if seconds < 60:
    return f"{seconds}s"
  if seconds < 3600:
    return f"{seconds // 60}m{seconds % 60:02d}s"
  return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


class CheckSummary:
  """The resolved rollup for a PR: one entry per check name."""

  def __init__(self, runs: Sequence[CheckRun]) -> None:
    self.runs = list(runs)

  @property
  def failed(self) -> list[CheckRun]:
    return [r for r in self.runs if r.failed]

  @property
  def running(self) -> list[CheckRun]:
    return [r for r in self.runs if r.running]

  @property
  def finished(self) -> int:
    return len(self.runs) - len(self.running)

  def describe_failed(self) -> str:
    return ", ".join(f"{r.name} ({r.state})" for r in self.failed)

  def describe_running(self) -> str:
    return ", ".join(
      "{} ({})".format(r.name, r.state or "in progress") for r in self.running
    )


class CheckRun:
  """One resolved check, after collapsing duplicate/stale runs of the same name."""

  __slots__ = ("name", "state", "superseded")

  def __init__(self, name: str, state: str, superseded: Sequence[str] = ()) -> None:
    self.name = name
    self.state = state
    self.superseded = tuple(superseded)

  @property
  def failed(self) -> bool:
    return self.state in FAIL_STATES

  @property
  def running(self) -> bool:
    return self.state in PENDING_STATES

  @property
  def passed(self) -> bool:
    return self.state in OK_STATES

  def render(self) -> str:
    note = ""
    if self.superseded:
      note = " (ignored superseded {})".format(", ".join(self.superseded))
    return 'check "{}": {}{}'.format(self.name, self.state or "in progress", note)


def collapse_rollup(rollup: Sequence[dict[str, Any]]) -> CheckSummary:
  """
  Collapse a status rollup to one entry per check name.

  GitHub keeps superseded runs in the rollup. When a workflow is re-run, the
  old attempt (often CANCELLED) can still sit next to the new SUCCESS
  one. Taking the rollup literally then reports "cancelled" for a PR the web
  UI shows as green. So per name, a pass wins over a stale cancelled/failed
  attempt, and the log names whatever it ignored.

  The web UI counts the same result for its PR pill.
  """
  grouped: dict[str, list[str]] = {}
  order: list[str] = []
  for item in rollup:
    name = item.get("name") or item.get("context") or "(unnamed check)"
    state = (
      item.get("conclusion") or item.get("state") or item.get("status") or ""
    ).upper()
    if name not in grouped:
      grouped[name] = []
      order.append(name)
    grouped[name].append(state)

  runs = []
  for name in order:
    states = grouped[name]
    passed = [st for st in states if st in OK_STATES]
    if passed:
      chosen = passed[0]
      superseded = [st for st in states if st != chosen]
    else:
      failed = [st for st in states if st in FAIL_STATES]
      chosen = failed[0] if failed else states[0]
      superseded = [st for st in states if st != chosen]
    runs.append(CheckRun(name, chosen, superseded))
  return CheckSummary(runs)


def read_checks(pr: int) -> CheckSummary:
  """Read a PR's status rollup and collapse it per check name."""
  res = gh("pr", "view", str(pr), "--json", "statusCheckRollup")
  try:
    data = json.loads(res.text or "{}") or {}
  except ValueError:
    raise Fail(f"could not parse `gh pr view {pr}` output")
  # gh prints an object here. A wrapper or a stray line can hand back a list.
  # An AttributeError from that is not a useful thing to show a user
  if not isinstance(data, dict):
    raise Fail(f"`gh pr view {pr}` printed a {type(data).__name__}, not a JSON object")
  rollup = data.get("statusCheckRollup") or []
  if not isinstance(rollup, list):
    raise Fail(
      f"`gh pr view {pr}` returned a {type(rollup).__name__} for the check rollup"
    )
  return collapse_rollup(rollup)


def log_checks(log: Log, summary: CheckSummary, seen: dict[str, str]) -> None:
  """Report each check once per state change (so polling stays quiet)."""
  for run in summary.runs:
    key = "{}|{}".format(run.state, ",".join(run.superseded))
    if seen.get(run.name) == key:
      continue
    seen[run.name] = key
    if run.failed:
      log.error(run.render())
    elif run.running:
      log.warning(run.render())
    else:
      log.ok(run.render())


def wait_for_checks(
  log: Log,
  pr: int,
  interval: int,
  timeout: int,
  summary: CheckSummary,
  seen: dict[str, str],
) -> CheckSummary:
  """Poll until no check is still running, or the timeout expires."""
  started = time.time()
  total = len(summary.runs)
  last_beat = started
  while True:
    remaining = timeout - (time.time() - started)
    if remaining <= 0:
      raise Fail(
        f"timed out after {_duration(timeout)} waiting for PR #{pr} checks; "
        f"still running: {summary.describe_running()}"
      )

    log.status(
      f"waiting for checks... {summary.finished}/{total} finished "
      f"(elapsed {_duration(time.time() - started)})"
    )
    time.sleep(min(interval, remaining))

    summary = read_checks(pr)
    log.clear_status()
    log_checks(log, summary, seen)

    if summary.failed:
      raise Fail(f"PR #{pr} has failing check(s): {summary.describe_failed()}")
    if not summary.running:
      log.info(
        f"all {total} check(s) finished after {_duration(time.time() - started)}"
      )
      return summary

    # redirected output gets no status line, so emit a periodic heartbeat
    if not log.tty and time.time() - last_beat >= 60:
      last_beat = time.time()
      log.info(
        f"still waiting: {summary.finished}/{total} finished "
        f"(elapsed {_duration(time.time() - started)})"
      )


def pr_gate(
  log: Log,
  target: str,
  *,
  skip: bool,
  wait_timeout: int,
  wait_interval: int,
  dry_run: bool,
  require_pr: bool = True,
) -> int | None:
  """
  The PR gate: no PR, or a failing check, stops the run.

  The tool waits for still-running checks rather than guessing. A check that is
  not finished yet is not a failure. `--check-timeout 0` turns waiting off,
  and `--skip-pr-check` skips the gate entirely.
  """
  if skip:
    log.warning("--skip-pr-check set, skipping PR validation entirely")
    return None

  log.info(f"checking PR status for {target}")
  pr = find_open_pr(target)
  if pr is None:
    if require_pr:
      raise Fail(
        f"no open PR for branch {target}, cannot proceed without an "
        "associated PR (pass --skip-pr-check to bypass)"
      )
    log.warning(
      f"no open PR for {target}, continuing because the branch was named "
      "explicitly with --branch"
    )
    return None
  log.info(f"found PR #{pr}")

  seen: dict[str, str] = {}
  summary = read_checks(pr)
  log_checks(log, summary, seen)

  if not summary.runs:
    log.warning(f"PR #{pr} reports no status checks at all")
    return pr
  if summary.failed:
    raise Fail(f"PR #{pr} has failing check(s): {summary.describe_failed()}")

  if summary.running:
    if dry_run:
      log.info(
        f"would wait for {len(summary.running)} still-running check(s) "
        f"(up to {_duration(wait_timeout)}) before continuing"
      )
      return pr
    if wait_timeout <= 0:
      raise Fail(
        f"PR #{pr} has {len(summary.running)} still-running check(s) and "
        f"waiting is disabled (--check-timeout=0): {summary.describe_running()}"
      )
    log.info(
      f"{len(summary.running)} check(s) still running, waiting up to "
      f"{_duration(wait_timeout)} (polling every {wait_interval}s)"
    )
    summary = wait_for_checks(log, pr, wait_interval, wait_timeout, summary, seen)
    if summary.failed:
      raise Fail(f"PR #{pr} has failing check(s): {summary.describe_failed()}")

  log.ok(f"PR #{pr} checks ok")
  return pr


# ==== Step 3b: remove paths from every commit (git filter-repo) ==============


class PathStats:
  """What the -p/--path stage did, or would do.

  `commits` touch any of the paths, `files` were ever tracked under them,
  `rewritten` got a new sha, and `pruned` were dropped for becoming empty.
  """

  def __init__(self) -> None:
    self.paths: list[str] = []
    self.commits = 0
    self.files = 0
    self.rewritten = 0
    self.pruned: set[str] = set()


def _normalize_path(raw: str) -> str:
  """
  Make a user-typed path match what git records.

  Windows users type `uploads\\2024`, and git stores `uploads/2024`. An absolute
  path passes as long as it points inside the repo. Paths are
  always relative to the repo root, never to the current directory.
  """
  typed = raw.replace("\\", "/")
  if os.path.isabs(typed):
    root = git("rev-parse", "--show-toplevel").text
    path = os.path.relpath(os.path.normpath(typed), root).replace("\\", "/")
    if path.startswith("../"):
      raise Fail(f"{raw} is outside the repo ({root})")
    return path
  path = typed.strip()
  while path.startswith("./"):
    path = path[2:]
  path = path.strip("/")
  if not path:
    raise Fail("empty path given to --path/-p")
  return path


def path_touches(paths: Sequence[str]) -> tuple[int, int]:
  """(commits touching any path, distinct files ever tracked under them)."""
  commits = git("log", "--all", "--format=%H", "--", *paths).text.split()
  names = git(
    "log", "--all", "--name-only", "--format=", "--", *paths
  ).text.splitlines()
  return len(commits), len({name.strip() for name in names if name.strip()})


def _remotes_snapshot() -> dict[str, tuple[list[str], list[str]]]:
  """name -> (fetch urls, push urls), as filter-repo will find them."""
  snap: dict[str, tuple[list[str], list[str]]] = {}
  for line in git("remote", "-v", check=False).lines():
    parts = line.split()
    if len(parts) < 3:
      continue
    name, url, direction = parts[0], parts[1], parts[2].strip("()")
    fetch, push = snap.get(name, ([], []))
    (fetch if direction == "fetch" else push).append(url)
    snap[name] = (fetch, push)
  return snap


def _remotes_restore(log: Log, snap: dict[str, tuple[list[str], list[str]]]) -> None:
  """
  Put back the remotes filter-repo removed.

  It drops `origin` on purpose ("push back from a fresh clone"), because its
  normal use is a throwaway clone. This tool rewrites the working repo in
  place. Every remote therefore goes back as it was: url, extra urls, and push
  url included.
  """
  present = set(git("remote", check=False).lines())
  for name, (fetch, push) in snap.items():
    if name in present or not fetch:
      continue
    git("remote", "add", name, fetch[0])
    for extra in fetch[1:]:
      git("remote", "set-url", "--add", name, extra)
    if push and push[0] != fetch[0]:
      git("remote", "set-url", "--push", name, push[0])
    log.info(f"restored remote {name} -> {fetch[0]}")


def _filter_repo_map() -> tuple[int, set[str]]:
  """(commits filter-repo changed, commits it dropped for becoming empty)."""
  path = git("rev-parse", "--git-path", "filter-repo/commit-map", check=False).text
  changed = 0
  pruned: set[str] = set()
  try:
    with open(path, encoding="utf-8") as handle:
      next(handle, None)  # "old new" header
      for line in handle:
        parts = line.split()
        if len(parts) != 2 or parts[0] == parts[1]:
          continue
        if parts[1].strip("0"):
          changed += 1
        else:
          pruned.add(parts[0])
  except OSError:
    return 0, pruned
  return changed, pruned


def filter_paths(log: Log, cfg: Settings, *, apply: bool) -> PathStats:
  """
  Remove files and directories from every commit with `git filter-repo`.

  filter-repo rewrites all refs, not just the branch under cleanup. That is
  what "remove this from history" has to mean: content left on another branch
  or tag is still fetchable. filter-repo re-points tags itself, and annotated
  ones become new tag objects with the original tagger and message. This stage
  therefore only restores the remotes and re-fetches, leaving
  `origin/<default>` resolvable for the push.

  Commits that only touched the removed paths become empty and go. Messages
  stay byte for byte (--preserve-commit-hashes, --preserve-commit-encoding):
  this stage is about files, not wording.
  """
  stats = PathStats()
  stats.paths = [_normalize_path(p) for p in cfg.paths]
  for path in stats.paths:
    if not git("log", "--all", "--format=%H", "--", path, check=False).text.split():
      raise Fail(
        f"nothing in this repo's history matches {path!r} "
        "(paths are matched from the repo root)"
      )
  stats.commits, stats.files = path_touches(stats.paths)
  listed = ", ".join(stats.paths)

  if not apply:
    log.info(
      f"would remove {listed}: {stats.files} file(s) across {stats.commits} commit(s)"
    )
    return stats

  if which("git-filter-repo") is None:
    raise Fail(
      "git filter-repo is needed to remove paths but is not installed: "
      "pip install git-filter-repo  (see github.com/newren/git-filter-repo)"
    )

  write_backup(log, "filter-repo")
  remotes = _remotes_snapshot()
  args: list[str] = ["filter-repo", "--force", "--invert-paths"]
  for path in stats.paths:
    args += ["--path", path]
  args += ["--preserve-commit-hashes", "--preserve-commit-encoding"]

  log.info(f"removing {listed} from every branch and tag")
  try:
    git(*args)
  finally:
    _remotes_restore(log, remotes)
  stats.rewritten, stats.pruned = _filter_repo_map()
  log.ok(
    f"removed {listed}: {stats.files} file(s) gone, {stats.rewritten} commit(s) rewritten"
  )
  if stats.pruned:
    log.info(
      f"{len(stats.pruned)} commit(s) only touched those paths, so they are gone too"
    )

  if "origin" in git("remote", check=False).lines():
    git("fetch", "--prune", "origin", check=False)
  return stats


# ==== Step 4: history rewrite (was strip-history.bat) ========================


def write_backup(log: Log, label: str) -> str:
  """Bundle every ref before an irreversible rewrite, and return the path."""
  stamp = datetime.now(UTC).astimezone().strftime("%Y%m%dT%H%M%S")
  path = os.path.join(tempfile.gettempdir(), f"git-pre-{label}-{stamp}.bundle")
  log.info("creating backup bundle")
  git("bundle", "create", path, "--all")
  log.ok(f"backup written to {path}")
  return path


class RewriteStats:
  """What the rewrite did, or would do.

  `rewritten` commits were replaced, `signed` of those got a GPG signature,
  `skipped` stayed byte-identical, and `tags` were re-pointed at new commits.
  """

  def __init__(self) -> None:
    self.total = 0
    self.rewritten = 0
    self.signed = 0
    self.skipped = 0
    self.tags = 0
    self.seconds = 0.0
    self.old_tip = ""
    self.new_tip = ""
    self.changed = False

  def summary(self) -> str:
    return (
      f"{self.total} commit(s): {self.rewritten} rewritten, {self.signed} signed, "
      f"{self.skipped} untouched ({self.seconds:.1f}s)"
    )


def _split_ident(raw: bytes) -> tuple[str, str, str]:
  """'Name <email> 1700000000 +0800' -> (name, email, date)."""
  lt = raw.index(b" <")
  gt = raw.index(b">", lt)
  name = raw[:lt].decode("utf-8", "surrogateescape")
  email = raw[lt + 2 : gt].decode("utf-8", "surrogateescape")
  date = raw[gt + 2 :].decode("utf-8", "surrogateescape")
  return name, email, date


def _read_raw_object(proc: subprocess.Popen, sha: str) -> bytes:
  """Read one full object out of a long-lived `git cat-file --batch` process."""
  assert proc.stdin is not None and proc.stdout is not None
  proc.stdin.write(sha.encode() + b"\n")
  proc.stdin.flush()
  header = proc.stdout.readline().split()
  if len(header) < 3 or header[-1] == b"missing":
    raise Fail(f"git object not found: {sha}")
  size = int(header[2])
  return proc.stdout.read(size + 1)[:-1]


class Commit:
  """The parts of a raw commit we care about."""

  __slots__ = (
    "author",
    "committer",
    "has_sig",
    "identity",
    "msg",
    "parents",
    "sha",
    "tree",
  )

  def __init__(self, sha: str, raw: bytes, identity: tuple[str, str]) -> None:
    head, self.msg = raw.split(b"\n\n", 1)
    self.sha = sha
    self.identity = identity
    self.tree = ""
    self.parents: list[str] = []
    an = ae = ad = cn = ce = cd = ""
    self.has_sig = b"gpgsig" in head
    for line in head.split(b"\n"):
      if line.startswith(b"tree "):
        self.tree = line[5:].decode()
      elif line.startswith(b"parent "):
        self.parents.append(line[7:].decode())
      elif line.startswith(b"author "):
        an, ae, ad = _split_ident(line[7:])
      elif line.startswith(b"committer "):
        cn, ce, cd = _split_ident(line[10:])
    self.author: tuple[str, str, str] = (an, ae, ad)
    self.committer: tuple[str, str, str] = (cn, ce, cd)

  def claimed(self, my_emails: Sequence[str], bots: Sequence[str]) -> bool:
    """Is this commit ours (by email) or produced by a claimed name?"""
    an, ae, _ = self.author
    cn, _ce, _ = self.committer
    return ae in my_emails or an in bots or cn in bots

  def needs_rewrite(self, claim: bool, sign: bool, parents_moved: bool) -> bool:
    """Does this commit differ from the version we would write?"""
    if parents_moved:
      return True
    if not claim:
      return False
    new_name, new_email = self.identity
    an, ae, _ = self.author
    cn, ce, _ = self.committer
    return bool(
      self.new_msg() != self.msg
      or an != new_name
      or ae != new_email
      or cn != new_name
      or ce != new_email
      or (sign and not self.has_sig)
    )

  def new_msg(self) -> bytes:
    """Claimed commits keep only the subject line."""
    return self.msg.split(b"\n", 1)[0] + b"\n"


def rewrite_history(
  log: Log, cfg: Settings, *, apply: bool, rev: str = "HEAD"
) -> RewriteStats:
  """
  Rebuild the current branch commit-by-commit.

  A commit is "claimed" when its author email is one of ours, or its
  author/committer name is a claimed name. A claimed commit gets:
    * author + committer rewritten to the current git identity (dates kept).
    * message trimmed to its subject line.
    * re-signed with -S (unless SIGN_COMMITS is False).

  Everything else stays verbatim, though it gets a new hash whenever
  one of its ancestors moved.

  apply=False is strictly read-only: it creates nothing, signs nothing,
  no ref moves. In that mode we only need to know *whether* a rewrite is
  needed. Any commit after the first changed one also changes, so the walk
  can answer without building a single object.
  """
  t0 = time.time()
  stats = RewriteStats()

  new_name = git("config", "user.name", check=False).text
  new_email = git("config", "user.email", check=False).text
  if not new_name or not new_email:
    raise Fail("git user.name / user.email are not configured")
  if not cfg.claim_names:
    raise Fail("the claimed names are empty (nothing would ever be claimed)")
  identity = (new_name, new_email)

  # a half-finished rebase on top would corrupt everything downstream
  git("rebase", "--abort", check=False)

  revs = git("rev-list", "--reverse", "--topo-order", rev).text.split()
  if not revs:
    raise Fail("no commits on the current branch")
  stats.total = len(revs)
  stats.old_tip = revs[-1]

  my_emails = [new_email, *cfg.claim_emails]
  bots = cfg.claim_names
  read_only = "" if apply else " (read-only)"
  log.info(f"scanning {len(revs)} commit(s) as {new_name} <{new_email}>{read_only}")

  if not apply:
    stats_scan = _scan(log, cfg, revs, my_emails, bots, identity)
    stats_scan.total = stats.total
    stats_scan.old_tip = stats.old_tip
    stats_scan.seconds = time.time() - t0
    if stats_scan.changed:
      tags = tags_into(revs)
      if tags:
        log.info(
          f"{tags} tag(s) point into these commits and would move to the rewritten ones"
        )
    return stats_scan

  mapping: dict[str, str] = {}
  proc = subprocess.Popen(
    ["git", "cat-file", "--batch"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
  )
  progress = Progress(log, "rewriting", len(revs))
  try:
    for index, sha in enumerate(revs, 1):
      head_commit = Commit(sha, _read_raw_object(proc, sha), identity)
      claim = head_commit.claimed(my_emails, bots)
      parents_moved = any(mapping.get(p, p) != p for p in head_commit.parents)

      if not head_commit.needs_rewrite(claim, cfg.sign, parents_moved):
        mapping[sha] = sha
        stats.skipped += 1
      else:
        msg = head_commit.new_msg() if claim else head_commit.msg
        an, ae, ad = head_commit.author
        cn, ce, cd = head_commit.committer
        a2n, a2e = (new_name, new_email) if claim else (an, ae)
        c2n, c2e = (new_name, new_email) if claim else (cn, ce)
        env = dict(os.environ)
        env.update(
          GIT_AUTHOR_NAME=a2n,
          GIT_AUTHOR_EMAIL=a2e,
          GIT_AUTHOR_DATE=ad,
          GIT_COMMITTER_NAME=c2n,
          GIT_COMMITTER_EMAIL=c2e,
          GIT_COMMITTER_DATE=cd,
        )
        args: list[str] = [
          "-c",
          "commit.gpgsign=false",
          "commit-tree",
          head_commit.tree,
        ]
        for parent in head_commit.parents:
          args += ["-p", mapping[parent]]
        if claim and cfg.sign:
          args.append("-S")
        try:
          new_sha = git(*args, stdin=msg, env=env).text
        except ToolError as exc:
          if claim and cfg.sign:
            detail = (exc.err or "").splitlines()
            raise Fail(
              "could not sign commit {}: {}\n    {}".format(
                sha[:8],
                detail[-1] if detail else "gpg failed",
                "fix your GPG setup, or set SIGN_COMMITS = False "
                "at the top of this file",
              )
            )
          raise
        if not new_sha:
          raise Fail(f"commit-tree returned no hash for {sha[:8]}")
        mapping[sha] = new_sha
        stats.rewritten += 1
        if claim and cfg.sign:
          stats.signed += 1

      progress.step(index, stats.rewritten)
  finally:
    progress.done()
    if proc.stdin:
      proc.stdin.close()
    proc.wait()

  stats.new_tip = mapping[stats.old_tip]
  stats.changed = stats.new_tip != stats.old_tip
  stats.seconds = time.time() - t0

  if not stats.changed:
    log.ok("nothing to rewrite - " + stats.summary())
    return stats

  write_backup(log, "rewrite")

  git("update-ref", "HEAD", stats.new_tip, stats.old_tip)
  stats.tags = retarget_tags(log, mapping)
  log.ok("history rewritten: " + stats.summary())
  if stats.tags:
    log.ok(f"{stats.tags} tag(s) now point at the rewritten commits")
  return stats


def _tag_rows() -> list[tuple[str, str, str, str]]:
  """
  (refname, object sha, object type, peeled commit sha) for every tag.

  Space separated on purpose. Ref names cannot contain spaces, and the other
  three fields are hex or a single word. Unlike NUL separators this stays
  readable when -v echoes the command's output.
  """
  fmt = "%(refname) %(objectname) %(objecttype) %(*objectname)"
  rows = []
  for line in git(
    "for-each-ref", "--format=" + fmt, "refs/tags", check=False
  ).text.splitlines():
    parts = line.split()
    if len(parts) == 3:  # lightweight tag: nothing to peel, field is empty
      parts.append("")
    if len(parts) == 4:
      rows.append((parts[0], parts[1], parts[2], parts[3]))
  return rows


def local_tags() -> dict[str, str]:
  """refs/tags/x -> the sha that ref currently holds."""
  return {ref: obj for ref, obj, _obj_type, _peeled in _tag_rows()}


def tags_into(revs: Sequence[str]) -> int:
  """How many tags point at one of these commits (read-only estimate)."""
  targets = set(revs)
  count = 0
  for _ref, obj, obj_type, peeled in _tag_rows():
    commit = obj if obj_type == "commit" else peeled
    if commit and commit in targets:
      count += 1
  return count


def _retarget_tag(raw: bytes, new_commit: str) -> bytes:
  """Same tag object, same tagger, same message - aimed at a new commit."""
  lines = raw.split(b"\n")
  if not lines[0].startswith(b"object "):
    raise Fail("unexpected tag object, refusing to re-point it")
  lines[0] = b"object " + new_commit.encode()
  return b"\n".join(lines)


def retarget_tags(log: Log, mapping: dict[str, str]) -> int:
  """
  Keep tags on the commits they name after a rewrite.

  A rewrite gives every commit a new sha. A tag that stays put then names
  a commit the branch no longer contains. `git checkout v1` still works, and
  hands back the history that was just cleaned, removed files included.

  Annotated tags cannot change in place. The rewrite builds them anew as tag
  objects with the original tagger line and message. Every update-ref
  names the old value, so a tag that moved underneath us aborts the run
  instead of losing it.

  The rewrite touches only tags whose target commit moved. Every other tag keeps its
  exact object, sha included.
  """
  moved = 0
  for ref, obj, obj_type, peeled in _tag_rows():
    if obj_type == "commit":
      new = mapping.get(obj)
      if not new or new == obj:
        continue
      git("update-ref", ref, new, obj)
      shown = new
    elif obj_type == "tag" and peeled:
      new = mapping.get(peeled)
      if not new or new == peeled:
        continue
      raw = git("cat-file", "tag", obj).out
      rebuilt = git(
        "hash-object", "-t", "tag", "-w", "--stdin", stdin=_retarget_tag(raw, new)
      ).text
      if not rebuilt:
        raise Fail(f"could not rebuild tag {ref[len('refs/tags/') :]}")
      git("update-ref", ref, rebuilt, obj)
      shown = new
    else:
      continue  # a tag of a tree/blob/tag: nothing for us to follow
    moved += 1
    log.dim(f"    tag {ref[len('refs/tags/') :]} -> {head_short(shown)}")
  return moved


def remote_tags() -> dict[str, str]:
  """refs/tags/x -> the sha origin holds right now (no peeled ^{} entries)."""
  found: dict[str, str] = {}
  for line in git("ls-remote", "--tags", "origin", check=False).lines():
    sha, _, ref = line.partition("\t")
    if sha and ref.startswith("refs/tags/") and not ref.endswith("^{}"):
      found[ref] = sha
  return found


def sync_tags(log: Log, cfg: Settings, before: dict[str, str]) -> None:
  """
  Move origin's tags onto the rewritten commits.

  This pass considers only tags the rewrite moved, and only ones that already
  exist on origin. A local-only tag stays local, because publishing is a
  decision nobody asked this tool to make. The tool never deletes a tag.

  Each tag push carries a lease pinned to the value origin had a
  moment ago. A tag someone else moved mid-run thus fails the push instead of
  being overwritten.
  """
  rows = {ref: (obj, obj_type, peeled) for ref, obj, obj_type, peeled in _tag_rows()}
  moved = [
    ref for ref, (obj, _k, _p) in rows.items() if before.get(ref) not in (None, obj)
  ]
  if not moved:
    return

  ahead = remote_tags()
  pushable: list[str] = []
  local_only: list[str] = []
  unpublished: list[str] = []
  for ref in moved:
    obj, obj_type, peeled = rows[ref]
    if ref not in ahead:
      local_only.append(ref)  # never publish what was never there
      continue
    if ahead[ref] == obj:
      continue
    target = obj if obj_type == "commit" else peeled
    if not target or git("merge-base", "--is-ancestor", target, "HEAD", check=False).rc:
      # filter-repo rewrote every ref, but this run publishes one branch. A moved tag
      # would point into history none of origin's branches have, so it stays and we say so.
      unpublished.append(ref)
      continue
    pushable.append(ref)

  def names(refs: list[str]) -> str:
    return ", ".join(ref[len("refs/tags/") :] for ref in refs)

  if local_only:
    log.dim("    local-only tag(s) not published: " + names(local_only))
  if unpublished:
    log.warning(
      f"{len(unpublished)} tag(s) not moved on origin - they point into history "
      f"this run does not publish: {names(unpublished)}"
    )
    log.dim("    clean that branch too (-b <branch> -p <path>) to move them")
  if not pushable:
    return

  if cfg.no_tags:
    log.warning(
      f"--no-tags set: {len(pushable)} tag(s) still name the old history "
      f"on origin: {names(pushable)}"
    )
    log.warning("the removed content stays reachable through those tags")
    return

  for ref in pushable:
    name = ref[len("refs/tags/") :]
    git("push", f"--force-with-lease={ref}:{ahead[ref]}", "origin", ref)
    log.ok(f"moved tag {name} {ahead[ref][:8]} -> {rows[ref][0][:8]}")
  log.ok(f"updated {len(pushable)} tag(s) on origin")


def warn_stale_remote_branches(log: Log, cfg: Settings, published: str) -> None:
  """
  Say which other branches on origin still contain the removed paths.

  filter-repo rewrites every ref locally, but this tool publishes exactly one
  branch. Everything else on origin keeps its old commits - and with them the
  files that were just removed. Silence there would read as "the repo is
  clean now", which it is not.
  """
  if not cfg.paths:
    return
  refs = git(
    "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin", check=False
  ).lines()
  stale = []
  for ref in refs:
    if ref in (f"origin/{published}", "origin/HEAD"):
      continue
    if git("log", "--format=%H", "-1", ref, "--", *cfg.paths, check=False).text.strip():
      stale.append(ref)
  if not stale:
    return
  paths = ", ".join(cfg.paths)
  log.warning(
    f"{len(stale)} other branch(es) on origin still contain {paths} "
    "- this run publishes one branch"
  )
  for ref in stale:
    log.dim("    " + ref)
  log.info("clean one too with: arena-cleanup -b <branch> -p <path>")


def _scan(
  log: Log,
  cfg: Settings,
  revs: Sequence[str],
  my_emails: Sequence[str],
  bots: Sequence[str],
  identity: tuple[str, str],
) -> RewriteStats:
  """Read-only answer to "would this branch be rewritten?"."""
  stats = RewriteStats()
  proc = subprocess.Popen(
    ["git", "cat-file", "--batch"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
  )
  progress = Progress(log, "scanning", len(revs))
  dirty = False
  try:
    for index, sha in enumerate(revs, 1):
      if dirty:
        # every descendant of a rewritten commit is rewritten too
        stats.rewritten += 1
      else:
        commit = Commit(sha, _read_raw_object(proc, sha), identity)
        claim = commit.claimed(my_emails, bots)
        if commit.needs_rewrite(claim, cfg.sign, False):
          dirty = True
          stats.rewritten += 1
          if claim and cfg.sign and not commit.has_sig:
            stats.signed += 1
        else:
          stats.skipped += 1
      progress.step(index, stats.rewritten)
  finally:
    progress.done()
    if proc.stdin:
      proc.stdin.close()
    proc.wait()
  stats.changed = dirty
  return stats


class Progress:
  """
  Progress for the commit walk.

  On a terminal: one line, redrawn in place - no scrollback spam.
  Captured output: a line every 25%, so logs stay readable.
  Either way it reports how many commits have been rewritten, which is the
  number that matters. Untouched commits get no line.
  """

  def __init__(self, log: Log, verb: str, total: int) -> None:
    self.log = log
    self.verb = verb
    self.total = max(total, 1)
    # in verbose mode git's own output streams to the terminal, so an
    # in-place redraw would fight with it. Fall back to plain lines
    self.mode = "line" if (log.tty and not log.verbose) else "tiered"
    self.next_tier = 25

  def step(self, index: int, rewritten: int) -> None:
    pct = index * 100 // self.total
    if self.mode == "line":
      text = f"{self.verb}... {pct}% ({index}/{self.total})"
      if rewritten:
        text += f" - {rewritten} rewritten"
      self.log.status(text)
    elif index == self.total or pct >= self.next_tier:
      self.next_tier = (pct // 25 + 1) * 25
      note = f" - {rewritten} rewritten" if rewritten else ""
      self.log.info(f"{self.verb}... {pct}% ({index}/{self.total}){note}")

  def done(self) -> None:
    self.log.clear_status()


# ==== Subcommands ============================================================


def delete_local_branch(log: Log, name: str, default: str, dry_run: bool) -> None:
  """Drop the local copy. This leaves the upstream branch alone."""
  if not branch_exists(f"refs/heads/{name}"):
    return
  if dry_run:
    log.warning(f"would delete local branch {name}")
    return
  if current_branch().lower() == name.lower():
    log.warning(
      f"local branch {name} is still checked out, not deleted "
      f"(switch off it, then: git branch -D {name})"
    )
    return
  res = git("branch", "-D", name, check=False)
  if res.rc != 0:
    raise ToolError(
      res.argv,
      res.rc,
      res.out,
      res.err,
      context=f"could not delete local branch {name}",
    )
  log.ok(f"deleted local branch {name}")


def delete_remote_branch(
  log: Log, name: str, default: str, dry_run: bool, pr: int | None
) -> None:
  """Drop origin/<name>. Only ever called with an arena/* branch."""
  if not name.startswith(ARENA_PREFIX) or name.lower() == default.lower():
    return
  if dry_run:
    log.warning(f"would delete origin/{name}")
    return
  if pr is not None:
    log.warning(f"deleting {name} also closes PR #{pr} on GitHub")
  res = git("push", "origin", "--delete", name, check=False)
  blob = (res.errtext + res.text).lower()
  if res.rc != 0 and "remote ref does not exist" in blob:
    log.info(f"origin/{name} is already gone")
  elif res.rc != 0:
    raise ToolError(
      res.argv, res.rc, res.out, res.err, context=f"could not delete origin/{name}"
    )
  else:
    log.ok(f"deleted origin/{name}")
  git("fetch", "--prune", "origin", check=False)  # clear the tracking ref


def _cancel(log: Log, started_on: str, dry_run: bool) -> int:
  """Undo the branch switch and stop: 'no' means the repo is left as found."""
  current = current_branch()
  if not dry_run and started_on and current and current != started_on:
    log.info(f"returning to {started_on}")
    res = git("switch", started_on, check=False)
    if res.rc != 0:
      log.warning(
        "could not switch back to {}: {}".format(
          started_on, (res.errtext or res.text).splitlines()[:1] or ""
        )
      )
  log.error("cancelled: nothing was rewritten and nothing was pushed")
  return 1


def leave_for_deletion(log: Log, name: str, default: str, dry_run: bool) -> None:
  """
  Step off `name` before its deletion.

  git refuses to delete the branch you are standing on. When we are on the
  arena branch, hop back to the default branch first. That happens when the
  run began inside it, or when -b named it.
  """
  if dry_run or not name.startswith(ARENA_PREFIX):
    return
  if current_branch().lower() != name.lower():
    return
  log.info(f"switching to {default} first, so {name} can be deleted")
  res = git("switch", default, check=False)
  if res.rc != 0:
    raise ToolError(
      res.argv, res.rc, res.out, res.err, context=f"could not switch to {default}"
    )


def _finish_on_default(log: Log, default: str, dry_run: bool) -> None:
  if dry_run:
    log.info(f"would return to {default}")
    return
  log.info(f"returning to {default}")
  res = git("switch", default, check=False)
  if res.rc != 0:
    raise ToolError(
      res.argv,
      res.rc,
      res.out,
      res.err,
      context=f"failed to switch back to {default}",
    )
  log.info(f"resetting {default} to origin/{default}")
  res = git("reset", "--hard", f"origin/{default}", check=False)
  if res.rc != 0:
    raise ToolError(
      res.argv,
      res.rc,
      res.out,
      res.err,
      context=f"failed to reset {default} to origin/{default}",
    )


def dirty_files() -> list[str]:
  """Tracked files with uncommitted changes (untracked files are harmless here)."""
  res = git("status", "--porcelain", "--untracked-files=no", check=False)
  return res.lines()


def guard_dirty_tree(
  log: Log, dirty: Sequence[str], will_switch: bool, force: bool, dry_run: bool
) -> None:
  """
  Refuse to move the working tree out from under uncommitted changes.

  A dirty tree either makes the branch switch fail or lets it through. In the
  first case the log shows git's own error in full. In the second case the
  `git reset --hard` at the end of the run throws the changes away. Both are
  surprises, and the second one loses work.

  Cleaning the default branch in place is fine, because nothing moves. That is
  what `will_switch` distinguishes.
  """
  if not dirty or dry_run:
    return
  if not will_switch:
    log.warning(
      f"working tree has {len(dirty)} uncommitted change(s), nothing here "
      "moves the working tree, so they are left alone"
    )
    return
  log.error(
    f"working tree has {len(dirty)} uncommitted change(s) and this run "
    "switches branches:"
  )
  for line in dirty[:10]:
    log.dim("    " + line)
  if len(dirty) > 10:
    log.dim(f"    ... and {len(dirty) - 10} more")
  if force:
    log.warning("--force set, continuing. The final reset will discard those changes")
    return
  raise Fail(
    "commit or stash them first (git stash), or pass -f to continue and lose them"
  )


def same_content_as(default: str, rev: str) -> bool:
  """True when `rev`'s tree is identical to origin/<default>'s."""
  return git("diff", "--quiet", f"origin/{default}", rev, "--", check=False).rc == 0


def at_risk_on_origin(
  default: str, rev: str, ignore: set[str] | None = None
) -> list[str]:
  """
  Commits on origin/<default> that a push of `rev` would drop.

  Compared by hash first, then by (subject, author date). Commits that exist
  on origin under a rewritten hash are the same work and are not at risk. A
  new commit, say a maintenance commit made straight on the default branch,
  has no twin. The push would replace it.

  `ignore` holds commits the rewrite dropped on purpose because they only
  touched the removed paths. The push guard should not ask about those.
  """
  candidates = git(
    "log",
    "--reverse",
    "--format=%H|%h|%s|%at",
    f"{rev}..origin/{default}",
    check=False,
  ).lines()
  if not candidates:
    return []
  twins = set(git("log", "--format=%s|%at", rev, check=False).lines())
  at_risk = []
  for line in candidates:
    parts = line.split("|", 3)
    if len(parts) != 4:
      continue
    full, short, subject, when = parts
    if ignore and full in ignore:
      continue  # went away with the removed paths, not a surprise
    if f"{subject}|{when}" in twins:
      continue  # same commit, rewritten elsewhere
    at_risk.append(f"{short} {subject} {when}")
  return at_risk


def history_looks_published(default: str, rev: str) -> bool:
  """
  Has this branch's work already reached origin/<default>, in some rewritten form?

  The cleanup preserves each commit's subject and author date, so a rewritten
  commit is recognisable by that pair. Take every commit `rev` has and origin
  does not. If each has such a twin on origin, the branch already reached origin
  under different hashes. Re-publishing it would replace a good history with a
  fresh variant for no content change.
  """
  local_only = git(
    "log", "--format=%s|%at", f"origin/{default}..{rev}", check=False
  ).lines()
  if not local_only:
    return False  # nothing local-only: handled elsewhere
  on_origin = set(
    git("log", "--format=%s|%at", f"origin/{default}", check=False).lines()
  )
  return all(line in on_origin for line in local_only)


def _wrap_up(
  log: Log,
  cfg: Settings,
  args: argparse.Namespace,
  target_name: str,
  default: str,
  switched: bool,
  explicit: bool,
  pr: int | None,
  note: str = "done",
) -> int:
  """
  Shared tail of every successful run: land back on the default branch and
  dispose of the local arena branch. Add -d to drop the remote copy too.
  """
  keep = bool(getattr(args, "keep_branch", False))
  drop_remote = bool(getattr(args, "delete_branch", False))
  is_arena = target_name.startswith(ARENA_PREFIX)

  if switched:
    _finish_on_default(log, default, cfg.dry_run)
  elif explicit and not (is_arena and not keep):
    log.info(f"staying on {target_name}")

  if is_arena and not keep:
    leave_for_deletion(log, target_name, default, cfg.dry_run)
    if drop_remote and pr is None and not cfg.dry_run and not args.skip_pr_check:
      pr = find_open_pr(target_name)
    if drop_remote:
      delete_remote_branch(log, target_name, default, cfg.dry_run, pr)
    delete_local_branch(log, target_name, default, cfg.dry_run)

  log.ok(note)
  return 0


def cmd_run(args: argparse.Namespace, log: Log) -> int:
  cfg = Settings(args)
  started_on = ""
  require_repo()
  require_tools(log, gh_required=True)

  log.info(f"{PROG} {__version__} starting")
  log.info(cfg.describe())
  if args.branch and args.arena:
    raise Fail("--arena and --branch exclude each other")
  if cfg.dry_run:
    log.warning("dry run: no branch will be deleted, no ref will move, nothing pushed")

  git("fetch", "--prune", "origin")
  log.ok("fetched and pruned origin")

  default = default_branch(log)
  log.info(f"default branch: {default}")

  current = current_branch()
  if not current:
    raise Fail("HEAD is detached, a branch is required")
  started_on = current  # where to go back to if the user cancels
  log.info(f"current branch: {current}")

  # Refuse to move the working tree out from under uncommitted changes, before anything
  # moved. Landing on the arena branch and hopping back to the default branch both move.
  prospective = args.branch or current
  if not args.branch and current.lower() == default.lower():
    will_switch = True  # we will hop onto the arena branch
  else:
    will_switch = prospective.lower() != current.lower() or (
      prospective.startswith(ARENA_PREFIX) and not args.keep_branch
    )
  guard_dirty_tree(log, dirty_files(), will_switch, args.force, cfg.dry_run)

  drop_stale_local_branches(log, current, cfg.dry_run)

  # Target: --branch NAME cleans that branch directly, with no arena discovery and no PR.
  # Otherwise, from the default branch, hop onto the single origin/arena/* branch first.
  explicit = args.branch
  switched = False

  if explicit:
    target_name = explicit
    log.info(f"cleaning {target_name} directly (--branch)")
    target = ensure_branch(log, target_name, dry_run=cfg.dry_run)
  else:
    target_name = current
    target = "HEAD"
    if current.lower() == default.lower():
      log.info(f"on {default}, locating origin/{ARENA_PREFIX}* branch")
      local, remote_ref = select_arena_branch(log, args.arena)
      target_name = local
      switched = True
      target = ensure_branch(
        log, local, dry_run=cfg.dry_run, remote_ref=remote_ref, set_upstream=True
      )
    log.info(f"current branch: {target_name}")

  if not cfg.dry_run and not explicit:
    require_upstream()
  if not pull_latest(log, cfg, default):
    return _cancel(log, started_on, cfg.dry_run)

  # ----------------------------------------------------------------- publish
  publish = target if cfg.dry_run else "HEAD"
  cleaning_default = target_name.lower() == default.lower()

  # Removing paths means the branch is going to change on purpose. The
  # "nothing to publish" shortcuts below would then answer the wrong question.
  rewriting_paths = bool(cfg.paths)

  if (
    not rewriting_paths and not cleaning_default and already_published(default, publish)
  ):
    log.ok(
      f"origin/{default} already contains {target_name} ({head_short(publish)}), nothing to publish"
    )
    return _wrap_up(
      log,
      cfg,
      args,
      target_name,
      default,
      switched,
      explicit,
      None,
      note="done, nothing to do",
    )

  # Both patterns mean origin/<default> absorbed this branch after a cleanup. A rewrite
  # would republish the same files and replace what origin gained since, so stop.
  if (
    not rewriting_paths
    and not cleaning_default
    and history_looks_published(default, publish)
  ):
    at_risk = at_risk_on_origin(default, publish)
    if at_risk:
      log.warning(
        f"{target_name} and origin/{default} have different content, but every commit "
        f"this branch adds is already on {default} (rewritten)"
      )
      log.warning(
        f"origin/{default} also has {len(at_risk)} commit(s) this branch does not have:"
      )
      for line in at_risk[:10]:
        log.dim("    " + line)
      if len(at_risk) > 10:
        log.dim(f"    ... and {len(at_risk) - 10} more")
      log.warning(
        f"publishing {target_name} would replace origin/{default} and drop those commit(s)"
      )
      if not args.force and not confirm(
        log, f"Publish {target_name} over origin/{default} anyway?"
      ):
        log.info(
          f"declining to publish; {target_name} is already absorbed into {default}"
        )
        log.info(f"to clean {default} itself, run: arena-cleanup -b {default}")
        return _wrap_up(
          log,
          cfg,
          args,
          target_name,
          default,
          switched,
          explicit,
          None,
          note="done, nothing to publish",
        )
      log.warning("confirmed, publishing anyway")
    else:
      log.warning(
        f"{target_name} and origin/{default} have identical content but different history"
      )
      log.warning(
        f"origin/{default} already carries a cleaned-up version of these "
        "commits, so there is nothing to rewrite or push"
      )
      return _wrap_up(
        log,
        cfg,
        args,
        target_name,
        default,
        switched,
        explicit,
        None,
        note="done, nothing to publish",
      )

  pr = pr_gate(
    log,
    target_name,
    skip=args.skip_pr_check,
    wait_timeout=args.check_timeout,
    wait_interval=args.check_interval,
    dry_run=cfg.dry_run,
    require_pr=not explicit,
  )

  # Tag shas as they are right now. After the rewrite this is what tells us
  # which tags moved. Those are the ones origin has to be told about.
  tags_before = local_tags()

  paths = None
  if cfg.paths:
    paths = filter_paths(log, cfg, apply=not cfg.dry_run)

  stats = rewrite_history(log, cfg, apply=not cfg.dry_run, rev=publish)
  if not stats.changed and cfg.dry_run:
    log.ok("history already clean, nothing to rewrite")  # real runs already said so

  # "Nothing to rewrite" does not mean "nothing to publish". The branch may
  # still hold commits origin has never seen, or just lost paths.
  removed_paths = bool(paths and (paths.rewritten or paths.pruned or cfg.dry_run))
  if stats.changed or removed_paths or not already_published(default, publish):
    force_push(
      log,
      default,
      cfg.dry_run,
      rev=publish,
      force=args.force,
      ignore=paths.pruned if paths else None,
    )
  else:
    log.info(f"nothing to push: {target_name} already matches origin/{default}")

  if not cfg.dry_run:
    sync_tags(log, cfg, tags_before)
    warn_stale_remote_branches(log, cfg, default)

  return _wrap_up(log, cfg, args, target_name, default, switched, explicit, pr)


def cmd_strip(args: argparse.Namespace, log: Log) -> int:
  cfg = Settings(args)
  require_repo()
  require_tools(log)

  check_only = bool(getattr(args, "check", False))
  apply = not (check_only or cfg.dry_run)
  log.info(f"{PROG} strip {__version__}")
  log.info(cfg.describe())

  paths = None
  if cfg.paths:
    paths = filter_paths(log, cfg, apply=apply)

  stats = rewrite_history(log, cfg, apply=apply)

  if check_only:
    if stats.changed or (paths and paths.commits):
      log.warning("rewrite needed: " + stats.summary())
      return 7
    log.ok("nothing to do: " + stats.summary())
    return 0

  log.ok("done: " + stats.summary())
  return 0


def cmd_doctor(args: argparse.Namespace, log: Log) -> int:
  cfg = Settings(args)
  log.info(f"{PROG} doctor {__version__}")
  log.info(f"python: {sys.version.split()[0]} at {sys.executable}")

  rc = 0
  for tool in ("git", "gh"):
    path = which(tool)
    if path:
      log.ok(f"{tool}: {path}")
    else:
      log.error(f"{tool}: not found on PATH")
      rc = 1

  if which("git"):
    inside = git("rev-parse", "--is-inside-work-tree", check=False).text
    if inside == "true":
      branch = current_branch() or "(detached HEAD)"
      log.ok("repo: {}".format(git("rev-parse", "--show-toplevel").text))
      log.info(f"branch: {branch}  head: {head_short()}")
      log.info(
        "git identity: {} <{}>".format(
          git("config", "user.name", check=False).text or "?",
          git("config", "user.email", check=False).text or "?",
        )
      )
      remote = git("remote", "get-url", "origin", check=False).text
      log.info("origin: %s" % (remote or "(not configured)"))
      for branch_name in local_arena_branches():
        log.info(f"local {branch_name}")
      for branch_name in remote_arena_branches():
        log.info(f"remote {branch_name}")
      if cfg.sign:
        signing_key = git("config", "user.signingkey", check=False).text
        if not which("gpg"):
          log.warning(
            "gpg not found - re-signing will fail. Set "
            "SIGN_COMMITS = False at the top of the script"
          )
          rc = rc or 0
        else:
          log.ok("gpg present, user.signingkey=%s" % (signing_key or "(default key)"))
    else:
      log.warning("not inside a git repo (run me from one)")

  if which("git-filter-repo"):
    version = git("filter-repo", "--version", check=False).text.splitlines()
    log.ok("git-filter-repo: " + (version[0] if version else "present"))
  else:
    log.warning(
      "git-filter-repo: not found (only needed for --path/-p, pip install git-filter-repo)"
    )

  if which("gh"):
    auth = gh("auth", "status", check=False)
    if auth.rc == 0:
      log.ok("gh authenticated")
    else:
      # the UI can fix this. Point at the thing that fixes it rather than at
      # a shell the container may not give you
      log.error(
        "gh is not authenticated - open the Access panel in the web UI, "
        "or run `gh auth login` in the container"
      )
      log.block(auth.err or auth.out)
      rc = 1
    # signing in to gh does not configure git. An https remote needs this.
    # gh writes a host-scoped helper, not a bare credential.helper
    helpers = " ".join(
      git("config", "--global", "--get-all", key, check=False).text
      for key in (
        "credential.helper",
        "credential.https://github.com.helper",
        "credential.http://github.com.helper",
      )
    )
    https_remote = "https://" in git("remote", "get-url", "origin", check=False).text
    if https_remote and "gh" not in helpers:
      log.warning(
        "git has no gh credential helper - cloning/pushing over https will fail; "
        "open Access in the web UI and press 'Set up git credentials', "
        "or run `gh auth setup-git`"
      )

  log.info(cfg.describe())
  log.ok("doctor finished")
  return rc


# ============================== CLI ==========================================

EPILOG = """\
commands:
  run      full flow: cleanup -> PR gate -> rewrite -> push   (default)
  strip    rewrite/sign local history only (the old strip-history)
  doctor   check tools, repo, identity, and signing setup

examples:
  arena-cleanup                     clean up, rewrite, and publish (arena/* flow)
  arena-cleanup -n                  say what a run would do, change nothing
  arena-cleanup -b main             clean main itself, in place
  arena-cleanup -d                  publish, then drop the arena branch on origin too
  arena-cleanup -K                  keep the local arena branch after the run
  arena-cleanup -k                  skip the PR gate entirely
  arena-cleanup -x remote           never ask: overwrite local with upstream
  arena-cleanup strip               rewrite local history without touching origin
  arena-cleanup strip -c            report whether a rewrite is needed
  arena-cleanup doctor              is git/gh/identity/signing all in order?
  arena-cleanup -p uploads          ...and drop uploads/ from every commit, then publish
  arena-cleanup strip -p notes/ -p TODO.md
                                    rewrite locally, removing two paths
  arena-cleanup -p uploads -T       ...and leave tag positions on origin alone

removing paths rewrites every branch and tag in the repo (that is what
"remove it from history" means). A tag that pointed into the rewritten
commits is re-pointed at the new ones; a signed tag loses its signature in
the process and needs `git tag -s -f <name> <commit>` again.

the local arena branch is deleted once a run finishes, so the next session
starts clean; origin/arena/* is left alone unless you pass -d.

environment:
  NO_COLOR=1                        no ANSI colors
"""


def build_parser() -> argparse.ArgumentParser:
  """
  One parser for every command, so `arena-cleanup --help` lists every flag.
  Per-subcommand parsers hid `run`'s flags behind `arena-cleanup run --help`,
  which is where nobody looks for them.
  """
  parser = argparse.ArgumentParser(
    prog=PROG,
    usage="%(prog)s [command] [flags]",
    description="Arena branch cleanup + history rewrite in one command.",
    epilog=EPILOG,
    formatter_class=argparse.RawDescriptionHelpFormatter,
  )
  parser.add_argument(
    "command",
    nargs="?",
    default="run",
    choices=("run", "strip", "doctor"),
    help="what to do (default: run)",
  )

  group = parser.add_argument_group("flags")
  group.add_argument(
    "-n",
    "--dry-run",
    action="store_true",
    help="report what would happen and change nothing",
  )
  group.add_argument(
    "-v",
    "--verbose",
    action="store_true",
    help="show every git/gh command and its output instead of muting it",
  )
  group.add_argument(
    "-V", "--version", action="version", version="%(prog)s " + __version__
  )

  run_group = parser.add_argument_group("run")
  run_group.add_argument(
    "-b",
    "--branch",
    metavar="NAME",
    default=argparse.SUPPRESS,
    help="clean this branch directly instead of "
    "discovering arena/* (e.g. -b main), no PR required",
  )
  run_group.add_argument(
    "-a",
    "--arena",
    metavar="NAME",
    default=argparse.SUPPRESS,
    help="the origin/arena/* branch to clean when several exist "
    "(e.g. -a arena/session-2), answers the menu without a prompt",
  )
  run_group.add_argument(
    "-d",
    "--delete-branch",
    action="store_true",
    default=argparse.SUPPRESS,
    help="also delete the arena branch on origin, not just the local copy",
  )
  run_group.add_argument(
    "-K",
    "--keep-branch",
    action="store_true",
    default=argparse.SUPPRESS,
    help="keep the local arena branch (it is deleted by default once the run is done)",
  )
  run_group.add_argument(
    "-x",
    "--on-divergence",
    choices=("ask", "remote", "local"),
    default=argparse.SUPPRESS,
    metavar="WHEN",
    help="when local and upstream differ in content: "
    "ask (default), remote (overwrite local), or "
    "local (never ask, keep local)",
  )
  run_group.add_argument(
    "-f",
    "--force",
    action="store_true",
    default=argparse.SUPPRESS,
    help="no lease: push with git push --force even when origin/<default> moved "
    "during the run. Also run with uncommitted changes, which the final reset "
    "discards, and push over commits the run would drop",
  )
  run_group.add_argument(
    "-k",
    "--skip-pr-check",
    action="store_true",
    default=argparse.SUPPRESS,
    help="skip the PR gate entirely: no PR required, failing/running checks ignored",
  )
  run_group.add_argument(
    "-t",
    "--check-timeout",
    type=int,
    metavar="SECONDS",
    default=argparse.SUPPRESS,
    help="how long to wait for still-running PR checks (default 900; 0 = do not wait)",
  )
  run_group.add_argument(
    "-i",
    "--check-interval",
    type=int,
    metavar="SECONDS",
    default=argparse.SUPPRESS,
    help="seconds between PR check polls (default 1)",
  )

  path_group = parser.add_argument_group("paths (run and strip)")
  path_group.add_argument(
    "-p",
    "--path",
    action="append",
    dest="paths",
    metavar="PATH",
    default=argparse.SUPPRESS,
    help="remove PATH (file or directory) from every commit with git filter-repo; "
    "repeat for more than one",
  )

  run_group.add_argument(
    "-T",
    "--no-tags",
    action="store_true",
    default=argparse.SUPPRESS,
    help="do not move tags on origin, they keep naming the old history",
  )

  strip_group = parser.add_argument_group("strip")
  strip_group.add_argument(
    "-c",
    "--check",
    action="store_true",
    default=argparse.SUPPRESS,
    help="do not touch HEAD, exit 7 if a rewrite is needed",
  )

  return parser


def _given(args: argparse.Namespace, flag: str) -> bool:
  """Did the user pass this flag? (run/strip-only flags are SUPPRESSed.)"""
  return hasattr(args, flag)


def main(argv: Sequence[str] | None = None) -> int:
  global _log
  parser = build_parser()
  args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

  # flags that only mean something for one command
  if args.command != "strip" and _given(args, "check"):
    parser.error("--check/-c only applies to `strip`")
  if args.command == "doctor" and _given(args, "paths"):
    parser.error("--path/-p only applies to `run` and `strip`")
  if args.command != "run":
    for flag in (
      "branch",
      "delete_branch",
      "keep_branch",
      "skip_pr_check",
      "check_timeout",
      "check_interval",
      "force",
      "on_divergence",
      "no_tags",
    ):
      if _given(args, flag):
        parser.error(
          "--{}/-{} only applies to `run`".format(
            flag.replace("_", "-"),
            {
              "branch": "b",
              "delete_branch": "d",
              "keep_branch": "K",
              "skip_pr_check": "k",
              "check_timeout": "t",
              "check_interval": "i",
              "force": "f",
              "on_divergence": "x",
              "no_tags": "T",
            }[flag],
          )
        )

  args.paths = getattr(args, "paths", None) or []
  args.no_tags = getattr(args, "no_tags", False)
  args.check_timeout = getattr(args, "check_timeout", 900)
  args.check_interval = getattr(args, "check_interval", 1)
  args.branch = getattr(args, "branch", None)
  args.arena = getattr(args, "arena", "")
  args.delete_branch = getattr(args, "delete_branch", False)
  args.keep_branch = getattr(args, "keep_branch", False)
  args.force = getattr(args, "force", False)
  args.on_divergence = getattr(args, "on_divergence", "ask")
  args.skip_pr_check = getattr(args, "skip_pr_check", False)

  args.func = {"run": cmd_run, "strip": cmd_strip, "doctor": cmd_doctor}[args.command]

  log = Log(verbose=args.verbose)
  _log = log

  try:
    return args.func(args, log)
  except Fail as exc:
    log.error(str(exc))
    return 1
  except ToolError as exc:
    log.error(str(exc))
    if exc.out:
      log.block(exc.out)
    if exc.err:
      log.block(exc.err)
    if exc.streamed:
      log.error("(see the output above)")
    return 1
  except KeyboardInterrupt:
    log.warning("interrupted by user")
    return 130
  except Exception as exc:
    log.error(f"unexpected failure: {type(exc).__name__}: {exc}")
    if log.verbose:
      import traceback

      traceback.print_exc()
    else:
      log.info("re-run with -v to see the full traceback")
    return 1


if __name__ == "__main__":
  _enable_windows_ansi()
  sys.exit(main())
