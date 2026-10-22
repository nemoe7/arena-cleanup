#!/usr/bin/env python3
"""
Build a throwaway demo of the UI and serve it.

The fixture holds:

- five repositories, cloned by URL like a live install: an arena branch each,
  one with two, and one whose default branch moved on after the session
- origins that answer to `https://github.com/demo/<name>`, mapped onto the local
  bare repositories with `url.<path>.insteadOf`
- a stub `gh` that answers from files, signed in as the configured identity
- a git identity that matches the engine's constants, with the credential
  helper `gh auth setup-git` would write
- a throwaway GPG key when `gpg` is installed

Nothing touches the host's git, gh, or gpg state. The server runs with HOME,
GIT_CONFIG_GLOBAL, and GNUPGHOME inside the demo root, and without the host's
GH_TOKEN or GITHUB_TOKEN.

  python3 scripts/demo.py --port 8080
  python3 scripts/demo.py --root /tmp/demo --no-serve   # build only, print env

The stub gh reads the demo root's gh/ directory:

  gh/signed-in   present = `gh auth status` succeeds; `gh auth login` creates it.
  gh/slow        present = every branch has a PR whose check never finishes.
  gh/prs.json    the open PR and check rollup for each arena branch.
  gh/gpg-keys    key ids `gh api user/gpg_keys` reports.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

from ui.server import Registry, register_path

# The demo identity: the gitconfig the stub writes, and the author of the claimed commits.
ME_NAME = "nemoe7"
ME_EMAIL = "60245796+nemoe7@users.noreply.github.com"

PAGE_BASE = "https://github.com/demo"

SUCCESS = {"status": "COMPLETED", "conclusion": "SUCCESS"}
FAILURE = {"status": "COMPLETED", "conclusion": "FAILURE"}
PENDING = {"status": "IN_PROGRESS", "conclusion": ""}

# name, arena branches with their open PR (None = no PR), whether main moved
# on after the session
REPOS = [
  (
    "shop-web",
    [
      (
        "arena/session-3",
        {
          "number": 142,
          "title": "feat: checkout page",
          "statusCheckRollup": [
            {"name": "lint", **SUCCESS},
            {"name": "test", **SUCCESS},
            {"name": "build", **SUCCESS},
            {"name": "e2e", **SUCCESS},
          ],
        },
      )
    ],
    False,
  ),
  (
    "billing-api",
    [
      (
        "arena/session-1",
        {
          "number": 88,
          "title": "fix: proration rounding",
          "statusCheckRollup": [
            {"name": "lint", **SUCCESS},
            {"name": "test", **FAILURE},
            {"name": "build", **PENDING},
          ],
        },
      )
    ],
    False,
  ),
  ("docs-site", [("arena/session-2", None)], False),
  # main gained commits after the session: the publish guard stops the run
  (
    "infra-tools",
    [
      (
        "arena/session-4",
        {
          "number": 57,
          "title": "chore: pin the base image",
          "statusCheckRollup": [
            {"name": "lint", **SUCCESS},
            {"name": "test", **SUCCESS},
          ],
        },
      )
    ],
    True,
  ),
  # two sessions left their branches: a run needs a branch choice
  (
    "data-pipeline",
    [
      (
        "arena/session-5",
        {
          "number": 203,
          "title": "feat: incremental loads",
          "statusCheckRollup": [
            {"name": "lint", **SUCCESS},
            {"name": "test", **PENDING},
          ],
        },
      ),
      ("arena/session-6", None),
    ],
    False,
  ),
]

OTHER = ("other-dev", "other@example.com")
AGENT = ("arena-agent", "agent@arena.ai")
BOT = ("arena-ai-coding-agent[bot]", "bot@arena.ai")
ME = (ME_NAME, ME_EMAIL)
FIRST_COMMIT = datetime(2024, 1, 1, 10, tzinfo=timezone(timedelta(hours=8)))

# main: a plain project history, one commit a day, so the commits card has
# something to list. Subject, file, author.
MAIN_HISTORY = [
  ("chore: init", "README.md", OTHER),
  ("feat: project skeleton", "app.py", OTHER),
  ("docs: usage notes", "README.md", OTHER),
  ("feat: config loading", "config.py", ME),
  ("test: config loading", "tests/test_config.py", ME),
  ("fix: empty config file", "config.py", OTHER),
  ("feat: command line entry", "cli.py", OTHER),
  ("refactor: split the modules", "app.py", ME),
  ("ci: add the workflow", ".github/workflows/ci.yml", OTHER),
  ("fix: windows paths", "config.py", ME),
  ("feat: structured logging", "log.py", OTHER),
  ("docs: configuration reference", "README.md", OTHER),
  ("chore: bump the dependencies", "pyproject.toml", OTHER),
  ("fix: flaky timing test", "tests/test_config.py", ME),
]
# the arena branch: one session of mixed authorship, with bodies to trim
BRANCH_HISTORY = [
  ("feat: external contribution\n\nbody the human wrote", "docs.md", OTHER),
  ("feat: agent work\n\nlong body that should be trimmed", "app.py", AGENT),
  ("fix: mine already fine", "app.py", ME),
  ("chore: bot cleanup\n\nanother body to trim", "tests/test_config.py", BOT),
  ("feat: checkout form\n\nscaffolded from the issue", "checkout.py", AGENT),
  ("fix: review feedback", "checkout.py", OTHER),
  ("test: checkout form\n\ngenerated cases", "tests/test_checkout.py", AGENT),
  ("style: format the module", "app.py", BOT),
  ("docs: checkout notes", "docs.md", ME),
]
# a second, shorter session on the same default branch
SECOND_HISTORY = [
  ("feat: retry policy\n\nagent notes", "retry.py", AGENT),
  ("fix: batch size off by one", "retry.py", OTHER),
  ("test: retry policy\n\ngenerated cases", "tests/test_retry.py", BOT),
]
SESSIONS = [BRANCH_HISTORY, SECOND_HISTORY]
# what main gains after the session, when the repository asks for it
MAIN_LATER = [
  ("fix: quoting in the deploy script", "deploy.sh", OTHER),
  ("docs: release notes", "README.md", ME),
]

GH_STUB = '''#!/usr/bin/env python3
"""Demo stand-in for gh: state lives in files next to this script's data."""
import json
import sys
from pathlib import Path

STATE = Path(%(state)r)
LOGIN = %(login)r
args = sys.argv[1:]


def signed_in() -> bool:
  return (STATE / "signed-in").exists()


def need_auth() -> None:
  if not signed_in():
    print("You are not logged into any GitHub hosts. Run gh auth login.", file=sys.stderr)
    sys.exit(4)


def prs() -> list:
  if (STATE / "slow").exists():
    return [
      {
        "branch": "*",
        "number": 7,
        "title": "demo: a check that never finishes",
        "statusCheckRollup": [{"name": "build", "status": "IN_PROGRESS", "conclusion": ""}],
      }
    ]
  try:
    return json.loads((STATE / "prs.json").read_text())
  except (OSError, ValueError):
    return []


def with_url(pr: dict) -> dict:
  return {**pr, "url": "https://github.com/demo/%%s/pull/%%d" %% (pr.get("repo", "demo"), pr["number"])}


def flag(name: str) -> str:
  return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else ""


if args[:2] == ["auth", "status"]:
  if not signed_in():
    print("You are not logged into any GitHub hosts. Run gh auth login.", file=sys.stderr)
    sys.exit(1)
  if "--json" in args:
    host = {"state": "success", "active": True, "host": "github.com", "login": LOGIN,
            "tokenSource": "oauth_token", "scopes": "gist, read:org, repo"}
    print(json.dumps({"hosts": {"github.com": [host]}}))
  else:
    print("github.com")
    print("  \\u2713 Logged in to github.com account %%s (keyring)" %% LOGIN)
  sys.exit(0)
if args[:2] == ["auth", "login"]:
  token = sys.stdin.read().strip()
  if not token:
    print("no token on stdin", file=sys.stderr)
    sys.exit(1)
  (STATE / "signed-in").write_text("")
  sys.exit(0)
if args[:2] == ["auth", "logout"]:
  (STATE / "signed-in").unlink(missing_ok=True)
  sys.exit(0)
if args[:2] in (["auth", "setup-git"], ["pr", "status"]):
  sys.exit(0)
if args[:2] == ["pr", "list"]:
  need_auth()
  head = flag("--head")
  hits = [with_url(p) for p in prs() if p["branch"] in (head, "*")]
  print(json.dumps(hits[:1]))
  sys.exit(0)
if args[:2] == ["pr", "view"]:
  need_auth()
  number = int(args[2]) if len(args) > 2 and args[2].isdigit() else 0
  for pr in prs():
    if pr["number"] == number:
      print(json.dumps({"statusCheckRollup": pr["statusCheckRollup"]}))
      sys.exit(0)
  print("no pull requests found for %%d" %% number, file=sys.stderr)
  sys.exit(1)
if args[:2] == ["api", "user/gpg_keys"]:
  need_auth()
  try:
    sys.stdout.write((STATE / "gpg-keys").read_text())
  except OSError:
    pass
  sys.exit(0)
print("demo gh: unhandled: " + " ".join(args), file=sys.stderr)
sys.exit(1)
'''


def run(*argv: str, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
  result = subprocess.run(
    argv, cwd=cwd, env=env, text=True, capture_output=True, check=True
  )
  return result.stdout.strip()


def git_env(base: dict[str, str], name: str, email: str, date: str) -> dict[str, str]:
  return {
    **base,
    "GIT_AUTHOR_NAME": name,
    "GIT_AUTHOR_EMAIL": email,
    "GIT_AUTHOR_DATE": date,
    "GIT_COMMITTER_NAME": name,
    "GIT_COMMITTER_EMAIL": email,
    "GIT_COMMITTER_DATE": date,
  }


def write_gitconfig(path: Path, key_id: str) -> None:
  user = [f"  name = {ME_NAME}", f"  email = {ME_EMAIL}"]
  if key_id:
    user.append(f"  signingkey = {key_id}")
  lines = [
    "[user]",
    *user,
    "[init]",
    "  defaultBranch = main",
    "[commit]",
    "  gpgsign = false",
    "[advice]",
    "  detachedHead = false",
    '[credential "https://github.com"]',
    "  helper = !gh auth git-credential",
  ]
  if key_id:
    lines += ["[gpg]", "  program = gpg"]
  path.write_text("\n".join(lines) + "\n")


def make_key(gnupghome: Path) -> str:
  """A throwaway signing key; "" when gpg is missing or refuses."""
  if not shutil.which("gpg"):
    return ""
  gnupghome.mkdir(parents=True, exist_ok=True)
  gnupghome.chmod(0o700)
  env = {**os.environ, "GNUPGHOME": str(gnupghome)}
  try:
    subprocess.run(
      [
        "gpg",
        "--batch",
        "--quiet",
        "--passphrase",
        "",
        "--quick-generate-key",
        f"Demo Signer <{ME_EMAIL}>",
        "default",
        "default",
        "0",
      ],
      env=env,
      check=True,
      capture_output=True,
      text=True,
    )
    listing = run("gpg", "--list-secret-keys", "--with-colons", env=env)
  except (OSError, subprocess.CalledProcessError):
    return ""
  for line in listing.splitlines():
    fields = line.split(":")
    if fields[0] == "sec" and len(fields) > 4:
      return fields[4]
  return ""


def make_origin(
  root: Path,
  name: str,
  branches: list[tuple[str, Any]],
  later: bool,
  env: dict[str, str],
) -> Path:
  """A bare origin with arena branches of mixed authorship, seeded from a throwaway clone."""
  origin = root / "origins" / f"{name}.git"
  work = root / "seeds" / name
  origin.parent.mkdir(parents=True, exist_ok=True)
  work.parent.mkdir(parents=True, exist_ok=True)
  run("git", "init", "--bare", "--quiet", "-b", "main", str(origin), env=env)
  run("git", "clone", "--quiet", str(origin), str(work), env=env)
  # every clone names the GitHub URL, as a live install does. git rewrites it
  # to the bare repository for every fetch and push.
  page = f"{PAGE_BASE}/{name}"
  run("git", "remote", "set-url", "origin", page, cwd=work, env=env)
  run("git", "config", "--global", f"url.{origin}.insteadOf", page, env=env)
  (work / "README.md").write_text(f"# {name}\n")

  days = itertools.count()

  def commit(message: str, file: str, who: tuple[str, str]) -> None:
    (work / file).parent.mkdir(parents=True, exist_ok=True)
    with (work / file).open("a") as fh:
      fh.write(message.splitlines()[0] + "\n")
    run("git", "add", file, cwd=work, env=env)
    date = (FIRST_COMMIT + timedelta(days=next(days))).isoformat()
    run(
      "git",
      "commit",
      "--quiet",
      "--no-gpg-sign",
      "-m",
      message,
      cwd=work,
      env=git_env(env, who[0], who[1], date),
    )

  for entry in MAIN_HISTORY:
    commit(*entry)
  run("git", "push", "--quiet", "-u", "origin", "main", cwd=work, env=env)
  for (branch, _pr), history in zip(branches, SESSIONS, strict=False):
    run("git", "checkout", "--quiet", "-b", branch, cwd=work, env=env)
    for entry in history:
      commit(*entry)
    run("git", "push", "--quiet", "-u", "origin", branch, cwd=work, env=env)
    run("git", "checkout", "--quiet", "main", cwd=work, env=env)
  if later:
    for entry in MAIN_LATER:
      commit(*entry)
    run("git", "push", "--quiet", "origin", "main", cwd=work, env=env)
  return origin


def clone_repo(name: str, later: bool, registry: Registry, env: dict[str, str]) -> None:
  """Clone by URL into the managed directory, the way the add bar does."""
  page = f"{PAGE_BASE}/{name}"
  target = registry.clones / name
  run("git", "clone", "--quiet", page, str(target), env=env)
  entry, err = register_path(str(target), registry, source=page, managed=True)
  if not entry:
    raise SystemExit(f"demo: could not register {target}: {err}")
  if later:  # the clone has not pulled, so the card shows the drift too
    behind = f"HEAD~{len(MAIN_LATER)}"
    run("git", "reset", "--quiet", "--hard", behind, cwd=target, env=env)


def build(root: Path) -> dict[str, str]:
  """Create the fixture under root; return the environment the server needs."""
  home = root / "home"
  bin_dir = root / "bin"
  gh_state = root / "gh"
  for path in (home, bin_dir, gh_state, root / "data"):
    path.mkdir(parents=True, exist_ok=True)

  key_id = make_key(root / "gnupg")
  write_gitconfig(root / "gitconfig", key_id)
  (gh_state / "gpg-keys").write_text(f"{key_id}\n" if key_id else "")
  (gh_state / "signed-in").write_text("")
  (gh_state / "prs.json").write_text(
    json.dumps(
      [
        {"repo": name, "branch": branch, **pr}
        for name, branches, _later in REPOS
        for branch, pr in branches
        if pr
      ],
      indent=2,
    )
    + "\n"
  )
  stub = bin_dir / "gh"
  stub.write_text(GH_STUB % {"state": str(gh_state), "login": ME_NAME})
  stub.chmod(0o755)

  env = {
    **os.environ,
    "HOME": str(home),
    "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
    "GIT_CONFIG_GLOBAL": str(root / "gitconfig"),
    "ARENA_DATA": str(root / "data"),
  }
  if key_id:
    env["GNUPGHOME"] = str(root / "gnupg")
  else:
    env.pop("GNUPGHOME", None)
  # a token of the host would show up in the GitHub card; the stub needs none
  env.pop("GH_TOKEN", None)
  env.pop("GITHUB_TOKEN", None)

  registry = Registry(root / "data")
  for name, branches, later in REPOS:
    make_origin(root, name, branches, later, env)
    clone_repo(name, later, registry, env)
  return env


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
  parser.add_argument(
    "--root", help="demo directory; default: a fresh temp dir, removed on exit"
  )
  parser.add_argument("--host", default="0.0.0.0")
  parser.add_argument("--port", type=int, default=8080)
  parser.add_argument(
    "--no-serve", action="store_true", help="build the fixture, print its env, exit"
  )
  args = parser.parse_args()

  if args.root:
    root = Path(args.root).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
      print(f"demo: {root} exists and is not empty", file=sys.stderr)
      return 2
    root.mkdir(parents=True, exist_ok=True)
    temporary = False
  else:
    root = Path(tempfile.mkdtemp(prefix="arena-demo."))
    temporary = True

  env = build(root)
  print(f"demo root: {root}")
  print(f"gh flag:   {root / 'gh' / 'signed-in'}")
  print(
    "signing:   "
    + ("throwaway key" if env.get("GNUPGHOME") else "off (no gpg on PATH)")
  )
  if args.no_serve:
    for key in ("HOME", "PATH", "GIT_CONFIG_GLOBAL", "GNUPGHOME", "ARENA_DATA"):
      if key in env:
        print(f"export {key}={env[key]}")
    return 0

  server = subprocess.Popen(
    [
      sys.executable,
      str(HERE / "ui" / "server.py"),
      "--host",
      args.host,
      "--port",
      str(args.port),
    ],
    env=env,
  )
  signal.signal(signal.SIGTERM, lambda *_: server.terminate())
  try:
    return server.wait()
  except KeyboardInterrupt:
    server.terminate()
    return server.wait()
  finally:
    if temporary:
      shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
  raise SystemExit(main())
