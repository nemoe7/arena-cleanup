"""End-to-end tests for the rewrite engine against throwaway repos and a fake gh.

The tests run in file order and share the `world` fixture. Each one starts
from the repo state the previous one left behind.
"""

from __future__ import annotations

import re
import shutil
import stat
from pathlib import Path

import pytest

from .conftest import LOG_LINE, ME_EMAIL, SEED_COMMITS, World, project_version

MAIN_ONLY = 1
ARENA_COMMITS = SEED_COMMITS - MAIN_ONLY
FAST_SECONDS = 5
CHECK_TIMEOUT = 3
BUNDLE_GLOB = "git-pre-rewrite-*.bundle"
needs_gpg = pytest.mark.skipif(
  shutil.which("gpg") is None, reason="no gpg on this machine"
)
needs_filter_repo = pytest.mark.skipif(
  shutil.which("git-filter-repo") is None, reason="git-filter-repo not installed"
)


def test_dry_run_changes_nothing(world: World) -> None:
  world.git("checkout", "-q", "arena/session-1")
  before = world.rev()
  res = world.cleanup("run", "--dry-run")
  assert res.rc == 0
  assert world.rev() == before
  assert res.says("would push (with lease)")
  assert res.says("would delete stale local branch arena/stale")
  assert world.has_ref("refs/heads/arena/stale")
  res = world.cleanup("run", "--dry-run", "-f")
  assert res.says("would force-push (no lease)"), res.text
  assert world.rev() == before

  # on the default branch it must resolve the arena branch first and describe
  # THAT branch, without touching the working tree
  world.git("checkout", "-q", "main")
  res = world.cleanup("--dry-run")
  assert res.says("would switch to arena/session-1")
  assert res.says("would push (with lease) arena/session-1")
  assert world.git("branch", "--show-current") == "main"
  assert world.rev("main") == world.rev("origin/main")
  world.git("checkout", "-q", "arena/session-1")


def test_logging_format(world: World) -> None:
  world.git("checkout", "-q", "main")
  res = world.cleanup("--dry-run")
  world.git("checkout", "-q", "arena/session-1")
  assert any(LOG_LINE.match(line) for line in res.lines)
  assert res.strays() == []
  assert not re.search(r"^s+s*", res.text, re.MULTILINE), "progress mark spam is back"
  assert res.says("scanning... ")


def test_strip_rewrites_identity_dates_and_messages(world: World) -> None:
  res = world.cleanup("strip")
  assert res.rc == 0
  assert re.search(r"3 rewritten, \d+ signed, 2 untouched", res.text)
  assert world.rev() != world.old_tip
  assert world.git("rev-list", "--count", "main..HEAD") == str(ARENA_COMMITS)
  assert world.rev("HEAD~4") == world.orig_m0
  assert world.rev("HEAD~3") == world.orig_m1
  assert world.rev("HEAD~2") != world.rev("origin/arena/session-1~2")
  authors = world.git("log", "--format=%an|%ae", "HEAD")
  assert "arena-agent" not in authors and "arena-ai-coding-agent" not in authors
  assert (
    world.git("log", "-1", "--format=%an <%ae>", "HEAD~3")
    == "other-dev <other@example.com>"
  )
  assert (
    world.git("log", "-1", "--format=%B", "HEAD~3").splitlines()[-1]
    == "body the human wrote"
  )
  assert world.git("log", "-1", "--format=%B", "HEAD~2") == "feat: agent work"
  assert world.git("log", "-1", "--format=%B", "HEAD") == "chore: bot cleanup"
  assert world.git("log", "-1", "--format=%aI", "HEAD~2") == world.author_date_agent
  assert world.git("log", "-1", "--format=%cn <%ce>", "HEAD") == f"nemoe7 <{ME_EMAIL}>"
  assert (
    world.git("log", "-1", "--format=%s", "HEAD~3") == "feat: external contribution"
  )
  assert world.git("log", "-1", "--format=%an", "HEAD~3") == "other-dev"
  assert world.git("rev-list", "--count", "HEAD") == str(SEED_COMMITS)


def test_strip_is_idempotent_and_check_reports_clean(world: World) -> None:
  world.cleanup("strip")
  assert world.cleanup("strip", "--check").rc == 0
  tip = world.rev()
  world.cleanup("strip")
  assert world.rev() == tip
  assert len(list(world.tmp.glob(BUNDLE_GLOB))) == 1


def test_full_run_from_the_default_branch(world: World) -> None:
  world.git("checkout", "-q", "main")
  world.git("reset", "-q", "--hard", "origin/main", check=False)
  # make origin/arena/session-1 differ from main so there is work to publish
  world.git("checkout", "-q", "arena/session-1")
  world.agent_commit("chore: more bot work")
  world.git("push", "-q", "--force", "origin", "arena/session-1")
  world.git("checkout", "-q", "main")
  world.git("fetch", "-q", "--prune", "origin")
  world.gh_state("open")
  res = world.cleanup("-K")
  assert res.rc == 0, res.text
  assert res.says("switching to arena/session-1")
  assert res.says("pushing (with lease)")
  assert world.git("branch", "--show-current") == "main"
  assert world.rev("main") == world.rev("origin/main")
  assert not world.has_ref("refs/heads/arena/stale")
  assert world.rev("origin/main") == world.rev("arena/session-1")
  subjects = world.git("log", "--format=%s", "origin/main").splitlines()
  assert subjects.count("chore: more bot work") == 1
  assert "arena-agent" not in world.git("log", "--format=%an", "origin/main")


def test_second_run_is_a_clean_no_op(world: World) -> None:
  res = world.cleanup("-K")
  assert res.rc == 0, res.text
  assert res.says("already contains")
  assert not res.says("hint:"), "git's raw advice leaked into the log"
  assert not res.says("WARN", "fast-forward")
  assert res.says("rewritten version of origin/arena/session-1")
  assert res.strays() == []


def test_pr_gate(world: World) -> None:
  world.git("checkout", "-q", "arena/session-1")
  world.agent_commit("chore: bot work 2")
  world.gh_state("none")
  res = world.cleanup("run", "-K")
  assert res.rc == 1
  assert res.says("no open PR"), res.text
  assert world.cleanup("run", "--skip-pr-check", "--dry-run").rc == 0

  world.gh_state("failing")
  res = world.cleanup("run")
  assert res.rc == 1
  assert res.seconds <= FAST_SECONDS, "waited on a failing check"
  assert res.says('check "test": FAILURE'), res.text
  assert res.says("has failing check(s)")

  world.gh_state("bad-shape")
  res = world.cleanup("run")
  assert res.rc == 1
  assert res.says("printed a list, not a JSON object"), res.text
  assert "traceback" not in res.text.lower()

  world.gh_state("pending")
  res = world.cleanup("run", "--dry-run")
  assert res.rc == 0
  assert res.says("would wait for 1 still-running check"), res.text

  world.gh_state("pending")
  res = world.cleanup("run", "-K", "--check-interval", "1", "--check-timeout", "30")
  assert res.rc == 0
  assert res.says("still running, waiting up to"), res.text
  assert res.says('check "build": SUCCESS')
  assert res.says("all 1 check(s) finished")

  # the run above published this branch, so add work to get back past the early exit
  world.agent_commit("chore: work for the timeout test")
  world.gh_state("pending-forever")
  res = world.cleanup(
    "run", "-K", "--check-interval", "1", "--check-timeout", str(CHECK_TIMEOUT)
  )
  assert res.rc == 1
  assert res.says(f"timed out after {CHECK_TIMEOUT}s"), res.text
  assert res.says("still running: build")

  world.gh_state("pending-forever")
  res = world.cleanup("run", "-K", "--check-timeout", "0")
  assert res.rc == 1
  assert res.says("waiting is disabled")

  world.gh_state("pending-forever")
  res = world.cleanup("run", "--dry-run")
  assert res.rc == 0
  assert res.seconds <= FAST_SECONDS, f"dry run waited {res.seconds:.0f}s"


def test_failure_handling(world: World) -> None:
  world.git("checkout", "-q", "main")
  assert world.cleanup(cwd=world.origin).rc == 1
  world.git("checkout", "-q", "--detach", "HEAD")
  res = world.cleanup()
  assert res.rc == 1
  assert res.says("detached")
  world.git("checkout", "-q", "arena/session-1")


def test_verbose_output(world: World) -> None:
  res = world.cleanup("doctor", "-v")
  assert any(line.startswith("$ git") for line in res.lines)
  assert any(LOG_LINE.match(line) and "INFO" in line for line in res.lines)
  # -v must not cost us the captured output: lots of code parses it
  res = world.cleanup("strip", "-n", "-v")
  assert res.rc == 0
  assert not res.says("not inside a git repo"), "-v lost the parsed output"
  assert any(line.startswith("  | ") for line in res.lines)


@needs_gpg
def test_gpg_signing_with_a_real_key(world: World) -> None:
  world.git("checkout", "-q", "main")
  world.git("branch", "-q", "-D", "arena/sign", check=False)
  world.git("checkout", "-q", "-b", "arena/sign")
  world.agent_commit("chore: agent signed work\n\nbody")
  world.git(
    "commit",
    "-q",
    "--allow-empty",
    "-m",
    "chore: human work",
    "--author=other@example.com <other@example.com>",
    "--no-gpg-sign",
  )
  res = world.cleanup("strip")
  assert res.rc == 0
  assert res.says("1 signed"), res.text
  assert world.git("log", "-1", "--format=%G?", "HEAD~1") == "G"
  assert world.git("log", "-1", "--format=%G?", "HEAD") == "N"
  assert world.git("log", "-1", "--format=%s", "HEAD~1") == "chore: agent signed work"
  assert world.cleanup("strip", "--check").rc == 0
  world.agent_commit("chore: unsigned agent work")
  before = world.rev()
  env = dict(world.env, GNUPGHOME=str(world.root / "gnupg-empty"))
  res = world.cleanup("strip", env=env)
  assert res.rc == 1
  assert res.says("could not sign commit")
  assert res.says("fix your GPG setup")
  assert world.rev() == before
  assert not (Path(world.git("rev-parse", "--git-dir")) / "REBASE_HEAD").exists()
  world.git("checkout", "-q", "arena/session-1")


def test_doctor(world: World) -> None:
  res = world.cleanup("doctor")
  assert res.rc == 0
  assert res.says("git:")
  assert res.says("gh authenticated")


def test_force_push_lease_protects_the_default_branch(world: World) -> None:
  real_git = shutil.which("git")
  flag = world.root / "sabotaged"
  sha_file = world.root / "sabotaged-sha"
  wrapper = world.bin / "git"
  wrapper.write_text(
    "#!/usr/bin/env bash\n"
    "# sabotage: move origin/main after the tool's fetch, just before its push\n"
    f'if [ "$1" = "push" ] && [ ! -f "{flag}" ]; then\n'
    f'  touch "{flag}"\n'
    f'  SAB="$("{real_git}" -C "{world.origin}" rev-parse refs/heads/arena/session-1)"\n'
    f'  "{real_git}" -C "{world.origin}" update-ref refs/heads/main "$SAB"\n'
    f'  echo "$SAB" > "{sha_file}"\n'
    "fi\n"
    f'exec "{real_git}" "$@"\n'
  )
  wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
  try:
    world.git("checkout", "-q", "main")
    world.git("update-ref", "refs/heads/main", world.rev("origin/main"))
    world.git("checkout", "-q", "arena/session-1")
    world.agent_commit("chore: agent work for lease test")
    world.gh_state("open")
    res = world.cleanup("-K")
    assert res.rc == 1
    origin_main = world.git("-C", str(world.origin), "rev-parse", "refs/heads/main")
    assert origin_main == sha_file.read_text().strip()
    assert origin_main != world.rev()
    assert res.says("stale info"), res.text
    assert world.git("log", "-1", "--format=%ae") == ME_EMAIL
  finally:
    wrapper.unlink()


@needs_gpg
def test_no_lease_push_lands_when_the_default_branch_moved(world: World) -> None:
  real_git = shutil.which("git")
  flag = world.root / "sabotaged"
  wrapper = world.bin / "git"
  wrapper.write_text(
    "#!/usr/bin/env bash\n"
    "# sabotage: move origin/main after the tool's fetch, just before its push\n"
    f'if [ "$1" = "push" ] && [ ! -f "{flag}" ]; then\n'
    f'  touch "{flag}"\n'
    f'  SAB="$("{real_git}" -C "{world.origin}" rev-parse refs/heads/arena/session-1)"\n'
    f'  "{real_git}" -C "{world.origin}" update-ref refs/heads/main "$SAB"\n'
    "fi\n"
    f'exec "{real_git}" "$@"\n'
  )
  wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
  try:
    world.git("checkout", "-q", "main")
    world.git("update-ref", "refs/heads/main", world.rev("origin/main"))
    world.git("checkout", "-q", "arena/session-1")
    world.agent_commit("chore: agent work for the no-lease test")
    world.gh_state("open")
    res = world.cleanup("-K", "-f")
    assert res.rc == 0, res.text
    assert res.says("force-pushing (no lease)")
    assert not res.says("stale info")
    origin_main = world.git("-C", str(world.origin), "rev-parse", "refs/heads/main")
    assert origin_main == world.rev()
    assert world.git("log", "-1", "--format=%ae") == ME_EMAIL
  finally:
    wrapper.unlink()
  # the tests after this one expect unpublished work on the local arena branch
  world.git("checkout", "-q", "arena/session-1")
  world.agent_commit("chore: agent work after the no-lease push")
  world.git("checkout", "-q", "main")


def test_upstream_diverged_with_different_content(world: World) -> None:
  sibling = world.root / "sibling"
  world.git("clone", "-q", str(world.origin), str(sibling), cwd=world.root)
  world.git("checkout", "-q", "arena/session-1", cwd=sibling)
  (sibling / "upstream-only.txt").write_text("upstream only\n")
  world.git("add", "upstream-only.txt", cwd=sibling)
  world.git(
    "commit",
    "-q",
    "-m",
    "feat: work pushed straight to the arena branch",
    "--no-gpg-sign",
    cwd=sibling,
  )
  world.git("push", "-q", "origin", "arena/session-1", cwd=sibling)
  world.git("checkout", "-q", "main")
  world.git("fetch", "-q", "origin")
  main_before = world.rev("origin/main")
  world.gh_state("open")
  local_before = world.rev("arena/session-1")

  # no terminal -> cannot ask -> cancels rather than guessing, and puts the repo back
  res = world.cleanup("run", "-K")
  assert res.rc == 1
  assert res.says("have diverged"), res.text
  assert res.says("only on origin/arena/session-1")
  assert res.says("cancelled:")
  assert world.git("branch", "--show-current") == "main"
  assert world.rev("origin/main") == main_before
  assert world.rev("arena/session-1") == local_before
  assert not res.says("hint:")

  # -x local: keep local history, no question
  res = world.cleanup("run", "-K", "-x", "local")
  assert res.rc == 0
  assert res.says("--on-divergence=local: keeping local history"), res.text
  assert world.rev("origin/main") != main_before

  # -x remote: overwrite the (diverged) local copy with the remote, then publish
  world.git("checkout", "-q", "arena/session-1")
  (world.work / "local-only.txt").write_text("local-only edit\n")
  world.git("add", "local-only.txt")
  world.git(
    "commit",
    "-q",
    "-m",
    "feat: local-only work that -x remote discards",
    "--no-gpg-sign",
  )
  world.git("checkout", "-q", "main")
  res = world.cleanup("run", "-K", "-x", "remote", "-f")
  assert res.rc == 0, res.text
  assert res.says("replacing local arena/session-1 with origin/arena/session-1"), (
    res.text
  )
  assert (
    world.git_rc("diff", "--quiet", "origin/arena/session-1", "origin/main", "--") == 0
  )
  assert world.git_rc("cat-file", "-e", "origin/main:upstream-only.txt") == 0
  assert world.git_rc("cat-file", "-e", "origin/main:local-only.txt") != 0


def test_branch_main_cleans_the_default_branch_in_place(world: World) -> None:
  mode = world.root / "mode.git"
  work = world.root / "mode-work"
  world.git("init", "-q", "--bare", "-b", "main", str(mode), cwd=world.root)
  world.git("clone", "-q", str(mode), str(work), cwd=world.root)
  if world.key_id:
    world.git("config", "user.signingkey", world.key_id, cwd=work)
    world.git("config", "gpg.program", "gpg", cwd=work)
  world.git(
    "commit",
    "-q",
    "--allow-empty",
    "-m",
    "chore: init",
    "--author=other@example.com <other@example.com>",
    "--no-gpg-sign",
    cwd=work,
  )
  world.git(
    "commit",
    "-q",
    "--allow-empty",
    "-m",
    "feat: agent wrote straight to main\n\na body the agent wrote",
    "--author=arena-ai-coding-agent[bot] <bot@arena.ai>",
    "--no-gpg-sign",
    cwd=work,
  )
  world.git("push", "-q", "-u", "origin", "main", cwd=work)
  dirty_tip = world.rev(cwd=work)
  world.gh_state("none")

  res = world.cleanup("--branch", "main", "--dry-run", cwd=work)
  assert res.rc == 0
  assert res.says("cleaning main directly")
  assert not res.says("locating origin/arena"), "still did arena discovery"
  assert world.rev(cwd=work) == dirty_tip
  assert world.git("branch", "--show-current", cwd=work) == "main"

  res = world.cleanup("--branch", "main", cwd=work)
  assert res.rc == 0
  assert world.git("log", "-1", "--format=%ae", cwd=work) == ME_EMAIL
  assert (
    world.git("log", "-1", "--format=%B", cwd=work)
    == "feat: agent wrote straight to main"
  )
  assert world.rev("main", cwd=work) == world.rev("origin/main", cwd=work)
  assert world.git("branch", "--show-current", cwd=work) == "main"
  assert world.rev(cwd=work) != dirty_tip

  res = world.cleanup("--branch", "main", cwd=work)
  assert res.rc == 0
  assert res.says("nothing to push"), res.text
  assert not res.says("pushing ("), "pushed again for no reason"

  res = world.cleanup("--branch", "no-such-branch", cwd=work)
  assert res.rc == 1
  assert res.says("branch not found: no-such-branch")


def test_delete_branch_drops_the_arena_branch_once_published(world: World) -> None:
  work = world.root / "mode-work"
  world.git("checkout", "-q", "-b", "arena/mode-test", cwd=work)
  world.agent_commit("chore: agent work for deletion\n\nbody", cwd=work)
  world.git("push", "-q", "-u", "origin", "arena/mode-test", cwd=work)
  world.git("checkout", "-q", "main", cwd=work)
  world.gh_state("open")

  res = world.cleanup("--delete-branch", "--dry-run", cwd=work)
  assert res.rc == 0
  assert res.says("would delete origin/arena/mode-test"), res.text
  assert res.says("would delete local branch arena/mode-test")
  assert world.has_ref("refs/heads/arena/mode-test", cwd=work)

  res = world.cleanup("--delete-branch", cwd=work)
  assert res.rc == 0
  assert res.says("deleted origin/arena/mode-test"), res.text
  assert res.says("deleted local branch arena/mode-test")
  assert not world.has_ref("refs/heads/arena/mode-test", cwd=work)
  assert "arena/mode-test" not in world.remote_heads(cwd=work)

  # already-published branch + --delete-branch must still tidy up
  world.git("checkout", "-q", "-b", "arena/already-there", "main", cwd=work)
  world.git("push", "-q", "-u", "origin", "arena/already-there", cwd=work)
  world.git("checkout", "-q", "main", cwd=work)
  res = world.cleanup("--delete-branch", cwd=work)
  assert res.rc == 0
  assert "arena/already-there" not in world.remote_heads(cwd=work)

  # safety: the default branch is never a deletion candidate
  res = world.cleanup("--branch", "main", "--delete-branch", cwd=work)
  assert res.rc == 0
  assert not re.search(r"deleted (origin/|local branch )main", res.text), (
    "tried to delete main"
  )
  assert not res.says("nothing to delete"), "noisy refusal for a flag that cannot apply"
  assert world.has_ref("refs/heads/main", cwd=work)
  assert world.remote_heads(cwd=work).count("main") == 1

  # running from inside the arena branch: switch off it so the delete can finish
  world.git("checkout", "-q", "-b", "arena/still-on-it", "main", cwd=work)
  world.git("push", "-q", "-u", "origin", "arena/still-on-it", cwd=work)
  res = world.cleanup("--delete-branch", cwd=work)
  assert res.rc == 0
  assert res.says("switching to main first, so arena/still-on-it can be deleted"), (
    res.text
  )
  assert res.says("deleted origin/arena/still-on-it")
  assert not world.has_ref("refs/heads/arena/still-on-it", cwd=work)
  assert world.git("branch", "--show-current", cwd=work) == "main"
  world.git("checkout", "-q", "arena/session-1", check=False)


LONG_FLAGS = (
  "--branch",
  "--delete-branch",
  "--skip-pr-check",
  "--check-timeout",
  "--check-interval",
  "--dry-run",
  "--verbose",
  "--check",
  "--version",
  "--path",
  "--no-tags",
  "--arena",
)
SHORT_FLAGS = (
  "-b",
  "-a",
  "-d",
  "-k",
  "-t",
  "-i",
  "-n",
  "-v",
  "-c",
  "-V",
  "-p",
  "-T",
)
USAGE_ERROR = 2
STRIP_CHECK_CODES = {0, 7}


def test_help_screen_and_shorthands(world: World) -> None:
  res = world.cleanup("--help")
  assert res.rc == 0
  missing = [flag for flag in LONG_FLAGS if flag not in res.text]
  assert missing == []
  hidden = [short for short in SHORT_FLAGS if f"{short}," not in res.text]
  assert hidden == []
  assert "arena-cleanup -b main" in res.text, "no examples in help"
  assert res.says("the local arena branch is deleted once a run finishes")

  # shorthands must behave exactly like their long forms
  world.git("checkout", "-q", "main")
  res = world.cleanup("-n")
  assert res.rc == 0
  assert res.says("dry run:")
  res = world.cleanup("-b", "main", "-n")
  assert res.rc == 0
  assert res.says("cleaning main directly")
  res = world.cleanup("-V")
  assert res.rc == 0
  assert re.search(r"arena-cleanup \d+\.\d+\.\d+", res.text)
  assert res.text.split()[-1] == project_version()
  res = world.cleanup("doctor", "-v")
  assert any(line.startswith("$ ") for line in res.lines)
  assert world.cleanup("strip", "-c").rc in STRIP_CHECK_CODES

  # another command rejects flags that belong to one, with a clear message
  res = world.cleanup("strip", "-b", "main")
  assert res.rc == USAGE_ERROR
  assert re.search(r"only applies to .run.", res.text), res.text
  res = world.cleanup("doctor", "-c")
  assert res.rc == USAGE_ERROR
  assert re.search(r"only applies to .strip.", res.text)
  assert not world.cleanup("-d").says("only applies"), (
    "-d rejected on the default command"
  )


def test_blacklist_claims_a_bare_arena_author(world: World) -> None:
  world.git("checkout", "-q", "main")
  world.git("checkout", "-q", "-b", "arena/bl-check", "main")
  world.git(
    "commit",
    "-q",
    "--allow-empty",
    "-m",
    "feat: bare arena author\n\nbody to trim",
    "--author=arena <arena@example.com>",
    "--no-gpg-sign",
  )
  world.git(
    "commit",
    "-q",
    "--allow-empty",
    "-m",
    "chore: human commit",
    "--author=someone <someone@example.com>",
    "--no-gpg-sign",
  )
  assert world.cleanup("strip").rc == 0
  assert world.git("log", "-1", "--format=%ae", "HEAD~1") == ME_EMAIL
  assert world.git("log", "-1", "--format=%B", "HEAD~1") == "feat: bare arena author"
  assert world.git("log", "-1", "--format=%ae", "HEAD") == "someone@example.com"
  world.git("checkout", "-q", "main")
  world.git("branch", "-q", "-D", "arena/bl-check")


def test_claim_rules_come_from_git_config(world: World) -> None:
  world.git("checkout", "-q", "main")
  world.git("checkout", "-q", "-b", "arena/rules-check", "main")
  for subject, author in (
    ("chore: by someone", "someone <someone@example.com>"),
    ("feat: bare arena author", "arena <arena@example.com>"),
  ):
    world.git(
      "commit",
      "-q",
      "--allow-empty",
      "-m",
      subject,
      f"--author={author}",
      "--no-gpg-sign",
    )
  world.git("config", "--global", "--add", "arena.claim-name", "someone")
  try:
    assert world.cleanup("strip").rc == 0
    # the configured rule replaces the constant one, it does not extend it
    assert world.git("log", "-1", "--format=%ae", "HEAD~1") == ME_EMAIL
    assert world.git("log", "-1", "--format=%ae", "HEAD") == "arena@example.com"
  finally:
    world.git("config", "--global", "--unset-all", "arena.claim-name")
    world.git("checkout", "-q", "main")
    world.git("branch", "-q", "-D", "arena/rules-check")


def test_superseded_check_runs(world: World) -> None:
  world.git("checkout", "-q", "-b", "arena/superseded", "main")
  world.agent_commit("chore: agent work for check dedupe")
  world.gh_state("superseded")
  res = world.cleanup("run", "-K", "--dry-run")
  assert res.rc == 0
  assert res.says('check "build": SUCCESS'), res.text
  assert res.says("ignored superseded CANCELLED")
  assert not re.search(r"check.*CANCELLED$", res.text, re.MULTILINE), (
    "still aborting on the stale cancelled run"
  )

  world.gh_state("superseded-failing")
  res = world.cleanup("run", "-K", "--dry-run")
  assert res.rc == 1
  assert res.says('check "test": FAILURE')


def test_local_arena_branch_is_deleted_once_the_run_is_done(world: World) -> None:
  world.git("checkout", "-q", "main")
  world.git("checkout", "-q", "-b", "arena/cleanup-default", "main")
  world.agent_commit("chore: agent work to publish\n\nbody")
  world.git("push", "-q", "-u", "origin", "arena/cleanup-default")
  world.git("checkout", "-q", "main")
  world.only_arena("arena/cleanup-default")
  world.gh_state("open")
  res = world.cleanup()
  assert res.rc == 0, res.text
  assert res.says("deleted local branch arena/cleanup-default"), res.text
  assert not world.has_ref("refs/heads/arena/cleanup-default")
  assert world.remote_heads().count("arena/cleanup-default") == 1, (
    "remote branch was removed without -d"
  )
  assert world.git("branch", "--show-current") == "main"
  world.git("push", "-q", "origin", "--delete", "arena/cleanup-default")
  world.git("fetch", "-q", "--prune", "origin")

  # -K keeps it
  world.git("checkout", "-q", "-b", "arena/keepme", "main")
  world.agent_commit("chore: another agent commit\n\nbody")
  world.git("push", "-q", "-u", "origin", "arena/keepme")
  world.git("checkout", "-q", "main")
  world.only_arena("arena/keepme")
  assert world.cleanup("-K").rc == 0
  assert world.has_ref("refs/heads/arena/keepme")
  assert world.remote_heads().count("arena/keepme") == 1
  world.git("branch", "-q", "-D", "arena/keepme")
  world.git("push", "-q", "origin", "--delete", "arena/keepme")
  world.git("fetch", "-q", "--prune", "origin")

  # -d removes both, local copy included
  world.git("checkout", "-q", "-b", "arena/dropboth", "main")
  world.agent_commit("chore: agent work to drop\n\nbody")
  world.git("push", "-q", "-u", "origin", "arena/dropboth")
  world.git("checkout", "-q", "main")
  world.only_arena("arena/dropboth")
  assert world.cleanup("-d").rc == 0
  assert not world.has_ref("refs/heads/arena/dropboth")
  assert "arena/dropboth" not in world.remote_heads()


def test_uncommitted_changes(world: World) -> None:
  world.git("checkout", "-q", "main")
  world.git("fetch", "-q", "--prune", "origin")
  world.git("reset", "-q", "--hard", "origin/main")
  # a file that differs between main and the arena branch, edited but uncommitted
  conflict = world.work / "conflict.txt"
  conflict.write_text("main version\n")
  world.git("add", "conflict.txt")
  world.git("commit", "-q", "-m", "chore: add conflict.txt", "--no-gpg-sign")
  world.git("push", "-q", "origin", "main")
  world.git("checkout", "-q", "-b", "arena/conflict", "main")
  conflict.write_text("branch version\n")
  world.git("commit", "-q", "-am", "feat: branch edits conflict.txt", "--no-gpg-sign")
  world.git("push", "-q", "-u", "origin", "arena/conflict")
  world.git("checkout", "-q", "main")
  world.only_arena("arena/conflict")
  conflict.write_text("uncommitted local edit\n")  # would be lost by the final reset

  res = world.cleanup("-K")
  assert res.rc == 1
  assert res.says("uncommitted change(s) and this run switches branches"), res.text
  assert res.says("M conflict.txt")
  assert res.says("git stash")
  assert res.says("-f to continue")
  assert world.git("branch", "--show-current") == "main"
  assert world.has_ref("refs/heads/arena/conflict"), (
    "run did partial work before aborting"
  )

  # -f forces past the guard, and then git's own error is what the log shows
  res = world.cleanup("-K", "-f")
  assert res.rc == 1
  assert res.says("--force set, continuing")
  assert res.says("failed to switch to arena/conflict")
  assert res.says("  | "), "raw output not shown"
  assert re.search(r"would be overwritten|local changes", res.text, re.IGNORECASE)
  assert res.says("git switch arena/conflict")

  # cleaning the default branch in place moves nothing, so the tool allows it
  world.git("checkout", "-q", "--", "conflict.txt")
  world.git("clean", "-qfd")
  with conflict.open("a") as fh:
    fh.write("in-place edit\n")
  res = world.cleanup("-b", "main")
  assert res.rc == 0, res.text
  assert res.says("nothing here moves the working tree"), res.text
  assert conflict.read_text().splitlines()[-1] == "in-place edit"
  world.git("checkout", "-q", "--", "conflict.txt")
  world.git("push", "-q", "origin", "--delete", "arena/conflict", check=False)
  world.git("fetch", "-q", "--prune", "origin")


def test_local_arena_branch_is_the_pre_cleanup_copy(world: World) -> None:
  world.git("checkout", "-q", "main")
  world.only_arena()
  world.git("checkout", "-q", "-b", "arena/stale-copy", "main")
  world.agent_commit("feat: work that gets published\n\nbody")
  world.git("push", "-q", "-u", "origin", "arena/stale-copy")
  # publish a cleaned version of it to main ...
  world.git("checkout", "-q", "main")
  world.git("merge", "-q", "--ff-only", "arena/stale-copy")
  world.cleanup("strip")
  world.git("push", "-q", "--force", "origin", "main")
  # ...then put the local arena branch back to its pre-cleanup (upstream) state
  world.git("checkout", "-q", "arena/stale-copy")
  world.git("reset", "-q", "--hard", "origin/arena/stale-copy")
  world.git("checkout", "-q", "main")
  main_tip = world.rev("origin/main")
  res = world.cleanup("-K")
  assert res.rc == 0
  assert res.says("identical content but different history"), res.text
  assert res.says("already carries a cleaned-up version")
  assert world.rev("origin/main") == main_tip
  assert not res.says("pushing ("), "force-pushed anyway"
  world.git("branch", "-q", "-D", "arena/stale-copy", check=False)


def test_multiple_origin_arena_branches(world: World) -> None:
  world.git("checkout", "-q", "main")
  world.git("reset", "-q", "--hard", "origin/main")
  world.git("fetch", "-q", "--prune", "origin")
  world.only_arena()
  for name in ("multi-a", "multi-b"):
    world.git("checkout", "-q", "-b", f"arena/{name}", "main")
    world.agent_commit(f"chore: work on {name}")
    world.git("push", "-q", "-u", "origin", f"arena/{name}")
    world.git("checkout", "-q", "main")
  world.gh_state("open")

  res = world.cleanup()
  assert res.rc == 1
  assert res.says("2 origin/arena/* branches found"), res.text
  assert res.says("-a <branch>")
  assert world.git("branch", "--show-current") == "main"
  assert sum(b.startswith("arena/multi") for b in world.remote_heads()) == 2

  # with a terminal: it lists them and waits for an answer
  res = world.interactive("arena-cleanup", "2\n")
  assert res.rc == 0
  assert res.says("Which one should this run clean?"), res.text
  assert res.says("1) origin/arena/multi-a")
  assert res.says("switching to arena/multi-b")
  assert (
    world.git("log", "-1", "--format=%s", "origin/main") == "chore: work on multi-b"
  )
  assert world.remote_heads().count("arena/multi-a") == 1
  world.git("push", "-q", "origin", "--delete", "arena/multi-a", check=False)
  world.git("fetch", "-q", "--prune", "origin")

  # cancelling at the menu is not destructive
  for name in ("multi-c", "multi-d"):
    world.git("checkout", "-q", "-b", f"arena/{name}", "main")
    world.agent_commit(f"chore: work on {name}")
    world.git("push", "-q", "-u", "origin", f"arena/{name}")
  world.git("checkout", "-q", "main")
  tips_before = world.git("ls-remote", "--heads", "origin")

  # --arena answers the menu without a terminal and keeps the full flow
  res = world.cleanup("-n", "--arena", "arena/multi-d")
  assert res.rc == 0, res.text
  assert res.says("arena/multi-d"), res.text
  assert not res.says("Which one should this run clean?")
  res = world.cleanup("-n", "-a", "arena/nope")
  assert res.rc == 1
  assert res.says("origin/arena/nope is not an origin/arena/* branch"), res.text
  res = world.cleanup("-n", "-a", "arena/multi-d", "-b", "main")
  assert res.rc == 1
  assert res.says("--arena and --branch exclude each other"), res.text
  assert world.git("ls-remote", "--heads", "origin") == tips_before

  res = world.interactive("arena-cleanup", "c\n")
  assert res.rc == 1
  assert res.says("cancelled:")
  assert world.git("ls-remote", "--heads", "origin") == tips_before
  assert world.git("branch", "--show-current") == "main"
  for name in ("multi-c", "multi-d"):
    world.git("push", "-q", "origin", "--delete", f"arena/{name}", check=False)
  world.git("fetch", "-q", "--prune", "origin")


def test_divergence_prompt_answered_by_hand(world: World) -> None:
  sibling = world.root / "sibling"
  world.git("checkout", "-q", "main")
  world.git("branch", "-q", "-D", "arena/multi-b", check=False)
  world.only_arena()
  world.git("reset", "-q", "--hard", "origin/main")
  world.git("fetch", "-q", "--prune", "origin")
  # local branch: commit A, pushed ...
  world.git("checkout", "-q", "-b", "arena/div-prompt", "main")
  (world.work / "shared.txt").write_text("local version\n")
  world.git("add", "shared.txt")
  world.git(
    "commit",
    "-q",
    "-m",
    "feat: local writes shared.txt",
    "--author=arena-agent <agent@arena.ai>",
    "--no-gpg-sign",
  )
  world.git("push", "-q", "-u", "origin", "arena/div-prompt")
  # ... remote copy: someone else adds commit B on top ...
  world.git("fetch", "-q", "origin", cwd=sibling)
  world.git(
    "checkout", "-q", "-B", "arena/div-prompt", "origin/arena/div-prompt", cwd=sibling
  )
  (sibling / "shared.txt").write_text("remote version\n")
  world.git("add", "shared.txt", cwd=sibling)
  world.git(
    "commit", "-q", "-m", "feat: remote writes shared.txt", "--no-gpg-sign", cwd=sibling
  )
  world.git("push", "-q", "origin", "arena/div-prompt", cwd=sibling)
  # ... and local adds its own commit C, so neither side can fast-forward
  world.git("fetch", "-q", "origin")
  world.git("checkout", "-q", "arena/div-prompt")
  (world.work / "local-only.txt").write_text("local only\n")
  world.git("add", "local-only.txt")
  world.git(
    "commit",
    "-q",
    "-m",
    "feat: local adds local-only.txt",
    "--author=arena-agent <agent@arena.ai>",
    "--no-gpg-sign",
  )
  world.git("checkout", "-q", "main")
  world.only_arena("arena/div-prompt")
  world.gh_state("open")
  assert (
    world.git("rev-list", "--count", "origin/arena/div-prompt..arena/div-prompt") == "1"
  )
  assert (
    world.git("rev-list", "--count", "arena/div-prompt..origin/arena/div-prompt") == "1"
  )

  # answer "keep local": local history wins, the remote-only commit stays unpublished
  res = world.interactive("arena-cleanup -K -f", "2\n")
  assert res.rc == 0
  assert res.says("have diverged"), res.text
  assert res.says("Replace local history with")
  assert res.says("keeping local history")
  assert world.git("show", "origin/main:shared.txt") == "local version"
  assert world.git_rc("cat-file", "-e", "origin/main:local-only.txt") == 0

  # answer "overwrite local": the remote copy replaces local, and that gets published
  world.git("checkout", "-q", "arena/div-prompt")
  (world.work / "shared.txt").write_text("second local change\n")
  world.git("add", "shared.txt")
  world.git(
    "commit",
    "-q",
    "-m",
    "feat: second local change",
    "--author=arena-agent <agent@arena.ai>",
    "--no-gpg-sign",
  )
  world.git("checkout", "-q", "main")
  res = world.interactive("arena-cleanup -K -f", "1\n")
  assert res.rc == 0
  assert res.says("replacing local arena/div-prompt with origin/arena/div-prompt"), (
    res.text
  )
  assert world.git("show", "origin/main:shared.txt") == "remote version"
  assert world.git_rc("cat-file", "-e", "origin/main:local-only.txt") != 0

  # cancel: back to the branch the run started on, nothing published
  world.git("checkout", "-q", "arena/div-prompt")
  (world.work / "shared.txt").write_text("third local change\n")
  world.git("add", "shared.txt")
  world.git(
    "commit",
    "-q",
    "-m",
    "feat: third local change",
    "--author=arena-agent <agent@arena.ai>",
    "--no-gpg-sign",
  )
  world.git("checkout", "-q", "main")
  main_now = world.rev("origin/main")
  local_tip = world.rev("arena/div-prompt")
  res = world.interactive("arena-cleanup -K", "c\n")
  assert res.rc == 1
  assert res.says("cancelled:"), res.text
  assert world.git("branch", "--show-current") == "main"
  assert world.rev("origin/main") == main_now
  assert world.rev("arena/div-prompt") == local_tip

  world.git("checkout", "-q", "main")
  world.git("push", "-q", "origin", "--delete", "arena/div-prompt", check=False)
  world.git("fetch", "-q", "--prune", "origin")
  world.git("branch", "-q", "-D", "arena/div-prompt", check=False)


def test_default_branch_already_absorbed_the_branch(world: World) -> None:
  world.git("checkout", "-q", "main")
  world.only_arena()
  world.git("reset", "-q", "--hard", "origin/main")
  world.git("fetch", "-q", "--prune", "origin")
  # a branch with an agent commit, and its work published to main (rewritten)
  world.git("checkout", "-q", "-b", "arena/absorbed", "main")
  world.git(
    "commit",
    "-q",
    "--allow-empty",
    "-m",
    "feat: agent work that gets absorbed\n\nbody",
    "--author=arena-ai-coding-agent[bot] <bot@arena.ai>",
    "--no-gpg-sign",
  )
  world.git("push", "-q", "-u", "origin", "arena/absorbed")
  world.git("checkout", "-q", "main")
  world.gh_state("open")
  assert world.cleanup("-K").rc == 0  # publish + clean main
  # a maintenance commit made straight on main afterwards
  world.git("reset", "-q", "--hard", "origin/main")
  world.git(
    "commit",
    "-q",
    "--allow-empty",
    "-m",
    "chore: maintenance commit made on main",
    "--no-gpg-sign",
  )
  world.git("push", "-q", "origin", "main")
  maint_sha = world.git("rev-parse", "--short", "HEAD")
  # the local arena branch is still the pre-cleanup copy
  world.git("branch", "-q", "-f", "arena/absorbed", "origin/arena/absorbed")
  world.git("checkout", "-q", "main")
  world.git("fetch", "-q", "--prune", "origin")
  main_now = world.rev("origin/main")

  res = world.cleanup("-K")
  assert res.rc == 0
  assert res.says(
    "different content, but every commit this branch adds is already on main"
  ), res.text
  assert res.says("origin/main also has 1 commit(s) this branch does not have")
  assert res.says(maint_sha)
  assert res.says("would replace origin/main and drop those commit(s)")
  assert res.says("arena-cleanup -b main")
  assert world.rev("origin/main") == main_now
  assert world.git_rc("merge-base", "--is-ancestor", maint_sha, "origin/main") == 0
  assert not res.says("pushing ("), "pushed despite the risk"

  # -f insists, and that is a documented way to lose the maintenance commit
  res = world.cleanup("-K", "-f")
  assert res.rc == 0
  assert res.says("origin/main also has 1 commit(s)")
  assert world.rev("origin/main") == world.rev("arena/absorbed")
  assert world.git_rc("merge-base", "--is-ancestor", maint_sha, "origin/main") != 0


def test_push_guard_for_a_maintenance_commit_on_main(world: World) -> None:
  world.git("checkout", "-q", "main")
  world.git("checkout", "-q", "-b", "arena/new-work", "main")
  world.agent_commit("chore: new agent work")
  world.git("push", "-q", "-u", "origin", "arena/new-work")
  world.git("checkout", "-q", "main")
  world.only_arena("arena/new-work")
  # main is behind the branch, plus a commit made after the fork
  world.git("reset", "-q", "--hard", "origin/main")
  world.git(
    "commit",
    "-q",
    "--allow-empty",
    "-m",
    "chore: hotfix landed on main meanwhile",
    "--no-gpg-sign",
  )
  world.git("push", "-q", "origin", "main")
  world.git("fetch", "-q", "--prune", "origin")
  main_before = world.rev("origin/main")

  res = world.cleanup("-K", "--dry-run", "-f")
  assert res.says("a real run would push anyway (-f)"), res.text
  res = world.cleanup("-K", "--dry-run")
  assert res.says("a real run would stop here"), res.text
  assert world.rev("origin/main") == main_before

  res = world.cleanup("-K")
  assert res.rc == 1
  assert res.says("this push replaces origin/main"), res.text
  assert res.says("hotfix landed on main meanwhile")
  assert res.says("cancelled before pushing")
  assert world.rev("origin/main") == main_before

  # answered at the terminal: publish anyway
  res = world.interactive("arena-cleanup -K", "y\n")
  assert res.rc == 0
  assert res.says("confirmed, pushing anyway"), res.text
  assert world.rev("origin/main") == world.rev("arena/new-work")

  world.git("checkout", "-q", "main")
  world.git("reset", "-q", "--hard", "origin/main")
  for name in ("arena/new-work", "arena/absorbed"):
    world.git("push", "-q", "origin", "--delete", name, check=False)
    world.git("branch", "-q", "-D", name, check=False)
  world.git("fetch", "-q", "--prune", "origin")


def _tree(world: World, repo: Path, ref: str) -> list[str]:
  return world.git("-C", str(repo), "ls-tree", "-r", "--name-only", ref).splitlines()


def _commit_all(world: World, cwd: Path, subject: str, author: str) -> None:
  world.git("add", "-A", cwd=cwd)
  world.git(
    "commit", "-q", "-m", subject, f"--author={author}", "--no-gpg-sign", cwd=cwd
  )


OTHER_DEV = "other-dev <other@example.com>"
AGENT = "arena-agent <agent@arena.ai>"
REWRITE_NEEDED = 7


@needs_filter_repo
def test_path_removes_a_directory_from_history_and_tags_follow(world: World) -> None:
  world.git("checkout", "-q", "main")
  world.only_arena()
  world.git("reset", "-q", "--hard", "origin/main")
  world.git("fetch", "-q", "--prune", "origin")
  world.git("checkout", "-q", "-b", "arena/paths", "main")
  site = world.work / "site"
  (site / "uploads").mkdir(parents=True)
  (site / "index.html").write_text("page\n")
  (site / "uploads" / "secret.bin").write_text("secret\n")
  _commit_all(world, world.work, "feat: site and uploads", OTHER_DEV)
  with (site / "uploads" / "secret.bin").open("a") as fh:
    fh.write("more secret\n")
  _commit_all(world, world.work, "chore: touch only uploads", AGENT)
  with (site / "index.html").open("a") as fh:
    fh.write("page two\n")
  _commit_all(world, world.work, "feat: more site", AGENT)
  world.git("tag", "-a", "v-site", "-m", "site release")  # on the last commit
  world.git("tag", "tl", "HEAD~2")  # on the untouched first commit
  before_sha = world.rev()
  commits_before = int(world.git("rev-list", "--count", "HEAD"))

  res = world.cleanup("strip", "-n", "-p", "site/uploads")
  assert res.rc == 0
  assert res.says("would remove site/uploads: 1 file(s) across 2 commit(s)"), res.text
  assert world.rev() == before_sha
  assert (site / "uploads" / "secret.bin").is_file()

  res = world.cleanup("strip", "-n", "-p", "./site/uploads/")
  assert res.says("would remove site/uploads:"), res.text
  assert world.cleanup("doctor").says("git-filter-repo:")

  res = world.cleanup("strip", "-p", "no/such/path")
  assert res.rc == 1
  assert res.says("nothing in this repo's history matches 'no/such/path'")
  assert world.rev() == before_sha
  assert world.cleanup("strip", "-c", "-p", "site/uploads").rc == REWRITE_NEEDED

  res = world.cleanup("strip", "-p", "site/uploads")
  assert res.rc == 0
  tree = _tree(world, world.work, "HEAD")
  assert not any(p.startswith("site/uploads/") for p in tree)
  assert "site/index.html" in tree
  assert "chore: touch only uploads" not in world.git("log", "--format=%s").splitlines()
  assert commits_before - int(world.git("rev-list", "--count", "HEAD")) == 1
  assert world.git("remote").split() == ["origin"]
  assert world.git("cat-file", "-t", "v-site") == "tag"
  assert (
    world.git("tag", "-l", "--format=%(contents)", "v-site").splitlines()[0]
    == "site release"
  )
  assert world.git_rc("merge-base", "--is-ancestor", "v-site", "HEAD") == 0
  assert world.rev("tl") == world.rev("HEAD~1")
  assert re.search(r"\d+ tag\(s\) now point at the rewritten commits", res.text), (
    res.text
  )

  # there is no way to keep a commit that only touched the removed path
  res = world.cleanup("strip", "-p", "site/uploads", "-E")
  assert res.rc == USAGE_ERROR
  assert "unrecognized arguments: -E" in res.text, res.text
  assert world.cleanup("strip", "-p", "site/uploads", "--keep-empty").rc == USAGE_ERROR


@needs_filter_repo
def test_path_with_run_publishes_the_cleaned_tree_and_moves_tags(world: World) -> None:
  origin = world.origin
  world.git("checkout", "-q", "main")
  world.only_arena()
  world.git("reset", "-q", "--hard", "origin/main")
  world.git("fetch", "-q", "--prune", "origin")
  world.git("checkout", "-q", "-b", "arena/pub", "main")
  (world.work / "dist").mkdir()
  (world.work / "dist" / "bundle.bin").write_text("blob\n")
  _commit_all(world, world.work, "feat: add dist bundle", AGENT)
  world.git("tag", "-a", "v1", "-m", "release v1")
  world.git("push", "-q", "-u", "origin", "arena/pub")
  world.git("push", "-q", "origin", "refs/tags/v1")
  world.git("checkout", "-q", "main")
  tag_before = world.git("-C", str(origin), "rev-parse", "refs/tags/v1")
  main_before = world.rev("origin/main")

  res = world.cleanup("-K", "-k", "-p", "dist")
  assert res.rc == 0, res.text
  assert not res.says("cancelled before pushing"), "push guard fired on a pruned commit"
  assert not any(p.startswith("dist/") for p in _tree(world, origin, "main"))
  assert world.rev("origin/main") != main_before
  assert world.git("-C", str(origin), "cat-file", "-t", "refs/tags/v1") == "tag"
  assert world.git("-C", str(origin), "rev-parse", "refs/tags/v1") != tag_before
  assert (
    world.git_rc(
      "-C", str(origin), "merge-base", "--is-ancestor", "refs/tags/v1", "main"
    )
    == 0
  )
  assert res.says("updated 1 tag(s) on origin"), res.text
  world.git("push", "-q", "origin", "--delete", "arena/pub", check=False)
  world.git("branch", "-q", "-D", "arena/pub", check=False)
  world.git("reset", "-q", "--hard", "origin/main")
  world.git("fetch", "-q", "--prune", "origin")

  # Isolated repo: the only commit touching the path is already on main. After the
  # prune HEAD is an ancestor of origin/main again, and the push still drops it there.
  clean_origin = world.root / "clean-origin.git"
  clean_work = world.root / "clean-work"
  world.git("init", "-q", "--bare", "-b", "main", str(clean_origin), cwd=world.root)
  world.git("clone", "-q", str(clean_origin), str(clean_work), cwd=world.root)
  (clean_work / "base.txt").write_text("base\n")
  _commit_all(world, clean_work, "base", OTHER_DEV)
  world.git("push", "-q", "-u", "origin", "main", cwd=clean_work)
  (clean_work / "onlydir").mkdir()
  (clean_work / "onlydir" / "x.bin").write_text("x\n")
  _commit_all(world, clean_work, "only a blob", OTHER_DEV)
  world.git("push", "-q", "origin", "main", cwd=clean_work)
  world.git("fetch", "-q", cwd=clean_work)
  assert any(p.startswith("onlydir/") for p in _tree(world, clean_origin, "main"))
  res = world.cleanup("-b", "main", "-k", "-p", "onlydir", cwd=clean_work)
  assert res.rc == 0, res.text
  assert not any(p.startswith("onlydir/") for p in _tree(world, clean_origin, "main"))
  assert (
    "only a blob"
    not in world.git("-C", str(clean_origin), "log", "--format=%s", "main").splitlines()
  )

  # --no-tags: publish the branch but leave origin's tag where it is
  world.git("reset", "-q", "--hard", "origin/main")
  world.git("checkout", "-q", "-b", "arena/pub2", "main")
  (world.work / "dist2").mkdir()
  (world.work / "dist2" / "b.bin").write_text("blob\n")
  _commit_all(world, world.work, "feat: another blob", AGENT)
  world.git("tag", "-a", "v2", "-m", "release v2")
  world.git("push", "-q", "-u", "origin", "arena/pub2")
  world.git("push", "-q", "origin", "refs/tags/v2")
  world.git("checkout", "-q", "main")
  tag2_before = world.git("-C", str(origin), "rev-parse", "refs/tags/v2")
  res = world.cleanup("-K", "-k", "-p", "dist2", "-T")
  assert res.rc == 0, res.text
  assert re.search(
    r"--no-tags set: \d+ tag\(s\) still name the old history on origin: .*v2", res.text
  ), res.text
  assert res.says("the removed content stays reachable through those tags")
  assert world.git("-C", str(origin), "rev-parse", "refs/tags/v2") == tag2_before
  assert (
    world.git_rc(
      "-C", str(origin), "merge-base", "--is-ancestor", "refs/tags/v2", "main"
    )
    != 0
  )
  assert not any(p.startswith("dist2/") for p in _tree(world, origin, "main"))
  world.git("push", "-q", "origin", "--delete", "arena/pub2", check=False)
  world.git("branch", "-q", "-D", "arena/pub2", check=False)
  world.git("checkout", "-q", "main")
  world.git("reset", "-q", "--hard", "origin/main")
  world.git("fetch", "-q", "--prune", "origin")


@needs_filter_repo
def test_tags_only_move_when_their_history_was_published(world: World) -> None:
  # two branches on origin, uploads on both: the run publishes main only, so a
  # tag into develop must stay put
  origin = world.root / "multi-origin.git"
  work = world.root / "multi-work"
  dev = "dev <d@e.com>"
  world.git("init", "-q", "--bare", "-b", "main", str(origin), cwd=world.root)
  world.git("clone", "-q", str(origin), str(work), cwd=world.root)
  (work / "uploads").mkdir()
  (work / "uploads" / "s.bin").write_text("s\n")
  (work / "a.txt").write_text("a\n")
  _commit_all(world, work, "A: main + uploads", dev)
  world.git("tag", "-a", "tMain", "-m", "on main", cwd=work)
  world.git("checkout", "-q", "-b", "develop", cwd=work)
  (work / "d.txt").write_text("d\n")
  _commit_all(world, work, "B: develop work", dev)
  world.git("tag", "-a", "tDev", "-m", "on develop", cwd=work)
  (work / "uploads" / "s2.bin").write_text("s2\n")
  _commit_all(world, work, "C: develop + uploads", dev)
  world.git("push", "-q", "origin", "main", "develop", cwd=work)
  world.git("push", "-q", "origin", "refs/tags/tMain", "refs/tags/tDev", cwd=work)
  world.git("checkout", "-q", "main", cwd=work)
  dev_before = world.git("-C", str(origin), "rev-parse", "develop")
  tdev_before = world.git("-C", str(origin), "rev-parse", "refs/tags/tDev")
  tmain_before = world.git("-C", str(origin), "rev-parse", "refs/tags/tMain")

  res = world.cleanup("-b", "main", "-k", "-p", "uploads", cwd=work)
  assert res.rc == 0, res.text
  assert not any(p.startswith("uploads/") for p in _tree(world, origin, "main"))
  assert world.git("-C", str(origin), "rev-parse", "develop") == dev_before
  assert world.git("-C", str(origin), "rev-parse", "refs/tags/tDev") == tdev_before
  assert (
    world.git_rc(
      "-C", str(origin), "merge-base", "--is-ancestor", "refs/tags/tDev", "develop"
    )
    == 0
  )
  assert world.git("-C", str(origin), "rev-parse", "refs/tags/tMain") != tmain_before
  assert (
    world.git_rc(
      "-C", str(origin), "merge-base", "--is-ancestor", "refs/tags/tMain", "main"
    )
    == 0
  )
  assert res.says("1 tag(s) not moved on origin"), res.text
  assert res.says("does not push: tDev")
  assert res.says("1 other branch(es) on origin still contain uploads"), res.text
  assert res.says("origin/develop")
  assert res.says("-b <branch> -p <path>")
