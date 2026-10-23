#!/bin/sh
# The container has exactly one surface: the web UI. Every argument goes
# through to the UI server (--host, --port, --data).
set -eu

# The engine reads the identity from git config, so the environment seeds it only
# while the config is empty. A value set in the container survives a restart.
if [ -n "${GIT_AUTHOR_NAME:-}" ] && [ -z "$(git config --global user.name || true)" ]; then
  git config --global user.name "$GIT_AUTHOR_NAME"
fi
if [ -n "${GIT_AUTHOR_EMAIL:-}" ] && [ -z "$(git config --global user.email || true)" ]; then
  git config --global user.email "$GIT_AUTHOR_EMAIL"
fi

# gnupg wants its home to be private. Docker root may create the volume.
if [ -d "${HOME:-/home/arena}/.gnupg" ]; then
  chmod 700 "${HOME:-/home/arena}/.gnupg" 2>/dev/null || true
fi

exec python3 /app/ui/server.py "$@"
