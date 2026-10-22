"""The compose file, its .env contract, and the tailscale sidecar wiring."""

from __future__ import annotations

import json
import re

from .conftest import ROOT

COMPOSE = (ROOT / "docker-compose.yml").read_text()
ENV_EXAMPLE = (ROOT / ".env.example").read_text()
GITIGNORE = (ROOT / ".gitignore").read_text().splitlines()
DOCKERIGNORE = (ROOT / ".dockerignore").read_text().splitlines()
DOCKERFILE = (ROOT / "Dockerfile").read_text()
REQUIRED_ENV = ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "TS_AUTHKEY")
APP_ALIAS = "arena-app"
NODE_NAME = "arena-cleanup"


def test_every_compose_variable_is_offered_in_env_example() -> None:
  # every ${VAR} the compose file substitutes has to be documented. Without it
  # `up` runs with an empty name and the engine refuses the first rewrite.
  names = sorted(set(re.findall(r"\$\{([A-Z_][A-Z_0-9]*)", COMPOSE)))
  missing = [
    n for n in names if not re.search(rf"^#*\s*{n}=", ENV_EXAMPLE, re.MULTILINE)
  ]
  assert missing == []
  for name in REQUIRED_ENV:
    assert re.search(rf"^{name}=", ENV_EXAMPLE, re.MULTILINE), name


def test_the_app_mounts_only_its_home_volume() -> None:
  # clones live in the home volume. No host checkout is bind-mounted, so the
  # app service has that one volume and nothing from the host.
  app = COMPOSE.split("  arena-cleanup-tailscale:")[0]
  mounts = re.findall(r"^\s+- (.+):(/.+)$", app, re.MULTILINE)
  assert mounts == [("arena-home", "/home/arena")]


def test_the_registry_lives_on_the_home_volume() -> None:
  # repos.json and the clones sit under ARENA_DATA. Inside the named volume
  # they survive `up --build`; only `down -v` drops them.
  data_dir = re.search(r"^\s*ARENA_DATA=(\S+)", DOCKERFILE, re.MULTILINE).group(1)
  app = COMPOSE.split("  arena-cleanup-tailscale:")[0]
  volume, target = re.findall(r"^\s+- (.+):(/.+)$", app, re.MULTILINE)[0]
  assert data_dir.startswith(target + "/")
  assert re.search(rf"^volumes:\n(?:  .*\n)*  {volume}:", COMPOSE, re.MULTILINE)


def test_the_image_takes_the_cli_and_leaves_the_launcher() -> None:
  # the build context is an allow list. The CLI is in it, the Windows
  # launcher is not, and nothing opens the door for it.
  assert DOCKERIGNORE.index("*") < DOCKERIGNORE.index("!arena-cleanup.py")
  assert not any(
    line.startswith(("!arena-cleanup.cmd", "!*.cmd")) for line in DOCKERIGNORE
  )
  assert "COPY arena-cleanup.py /app/arena-cleanup.py" in DOCKERFILE


def test_env_files_stay_local() -> None:
  assert ".env" in GITIGNORE
  assert any(line.startswith(".env.*") for line in GITIGNORE)
  assert not any(line.startswith("!.env") for line in DOCKERIGNORE), (
    "the build context allows .env in"
  )
  assert "TS_AUTHKEY: ${TS_AUTHKEY" in COMPOSE


def test_the_sidecar_dials_a_dedicated_app_name() -> None:
  # the sidecar is hostnamed arena-cleanup for the MagicDNS name. Inside it
  # `arena-cleanup` is itself, so the proxy dials a name only the app answers.
  serve = json.loads((ROOT / "docker" / "tailscale-serve.json").read_text())
  proxies = re.findall(r'"Proxy": "http://([^:"]*):', json.dumps(serve, indent=1))
  assert proxies == [APP_ALIAS]
  assert re.search(rf"^\s+- {APP_ALIAS}$", COMPOSE, re.MULTILINE), (
    "compose lacks the app alias"
  )
  assert f"hostname: {NODE_NAME}" in COMPOSE
  assert NODE_NAME not in proxies
