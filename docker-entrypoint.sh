#!/bin/sh
# The container has exactly one surface: the web UI. Any argument is passed
# through to the UI server (--host, --port, --data).
set -eu

# Identity has to live in git config, because the engine reads it back. Seed it
# from the environment only while the config is empty. A value set in the
# container (Settings page or `git config --global`) survives a restart.
if [ -n "${GIT_AUTHOR_NAME:-}" ] && [ -z "$(git config --global user.name || true)" ]; then
  git config --global user.name "$GIT_AUTHOR_NAME"
fi
if [ -n "${GIT_AUTHOR_EMAIL:-}" ] && [ -z "$(git config --global user.email || true)" ]; then
  git config --global user.email "$GIT_AUTHOR_EMAIL"
fi

# gnupg wants its home to be private; the volume may be created by Docker root.
if [ -d "${HOME:-/home/arena}/.gnupg" ]; then
  chmod 700 "${HOME:-/home/arena}/.gnupg" 2>/dev/null || true
fi

# The one mistake that costs a re-login: running without the HOME volume. Say so
# at start-up, in the docker logs, where it will actually be read.
home="${HOME:-/home/arena}"
if ! grep -qs " ${home} " /proc/self/mountinfo; then
  echo "arena-cleanup: warning: $home is not a mount point." >&2
  echo "arena-cleanup: credentials and repos here are lost on the next docker rm." >&2
  echo "arena-cleanup: mount a volume, e.g. -v arena-home:$home" >&2
fi

exec python3 /app/ui/server.py "$@"
