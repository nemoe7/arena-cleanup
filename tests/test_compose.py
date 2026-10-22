"""The compose file, its .env contract, and the tailscale sidecar wiring."""

from __future__ import annotations

import json
import re

from .conftest import ROOT

COMPOSE = (ROOT / "docker-compose.yml").read_text()
ENV_EXAMPLE = (ROOT / ".env.example").read_text()
GITIGNORE = (ROOT / ".gitignore").read_text().splitlines()
DOCKERIGNORE = (ROOT / ".dockerignore").read_text().splitlines()
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
