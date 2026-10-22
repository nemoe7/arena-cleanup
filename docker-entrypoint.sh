#!/bin/sh
# The container has exactly one surface: the web UI. Any argument is passed
# through to the UI server (--host, --port, --data, --repo).
set -eu

# A repo bind-mounted from the host usually belongs to another uid, which git
# now refuses ("dubious ownership"). The mount is the point of the container.
# Trust it explicitly rather than asking every user to chown their work tree.
if ! git config --global --get-all safe.directory 2>/dev/null | grep -qx '\*'; then
  git config --global --add safe.directory '*'
fi

# Identity has to live in git config, because the engine reads it back. Seed it
# from the environment once; afterwards `git config --global` in the container
# wins.
if [ -n "${GIT_AUTHOR_NAME:-}" ]; then
  git config --global user.name "$GIT_AUTHOR_NAME"
fi
if [ -n "${GIT_AUTHOR_EMAIL:-}" ]; then
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
