# syntax=docker/dockerfile:1.7
#
# arena-cleanup - a web UI for cleaning Arena branches, amd64 and arm64.
#
#   docker buildx build --platform linux/amd64,linux/arm64 -t arena-cleanup .
#
# Runtime needs four tools. git 2.36+ supports --force-with-lease=<ref>:<expect>.
# gh reads PR checks and the GPG keys on your account.
#
# git-filter-repo removes paths. gnupg signs commits. All four are installed
# here, so the image is the whole environment. Nothing has to exist on the host.

FROM debian:13-slim AS base

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG GH_VERSION=2.62.0
ARG TARGETARCH

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
       ca-certificates curl git openssh-client gnupg2 python3 python3-pip \
  && rm -rf /var/lib/apt/lists/*

# gh: official static build, checksum verified, one URL per architecture
RUN case "$TARGETARCH" in \
      amd64) gh_arch=amd64 ;; \
      arm64) gh_arch=arm64 ;; \
      *) echo "unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac \
  && cd /tmp \
  && curl -fsSLO \
       "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${gh_arch}.tar.gz" \
  && curl -fsSL -o gh_checksums.txt \
       "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_checksums.txt" \
  && grep " gh_${GH_VERSION}_linux_${gh_arch}.tar.gz$" gh_checksums.txt | sha256sum -c - \
  && tar -xzf "gh_${GH_VERSION}_linux_${gh_arch}.tar.gz" \
  && install -m 0755 "gh_${GH_VERSION}_linux_${gh_arch}/bin/gh" /usr/local/bin/gh \
  && rm -rf gh_*.tar.gz gh_checksums.txt "gh_${GH_VERSION}_linux_${gh_arch}"

# git-filter-repo: Debian's package is architecture-independent Python
RUN apt-get update \
  && apt-get install -y --no-install-recommends git-filter-repo \
  && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# A normal user with a home directory: gh, git, and gpg all want one.
# Rewriting history as root makes every object root-owned on the host.
RUN useradd --create-home --uid 1000 --shell /bin/bash arena

WORKDIR /app
COPY pyproject.toml /app/pyproject.toml
COPY engine.py /app/engine.py
COPY ui /app/ui

COPY docker-entrypoint.sh /usr/local/bin/arena-docker-entrypoint
RUN chmod +x /app/engine.py /usr/local/bin/arena-docker-entrypoint

ENV ARENA_REPO=/repo \
    ARENA_HOST=0.0.0.0 \
    ARENA_PORT=8080 \
    ARENA_DATA=/home/arena/.local/share/arena-cleanup \
    HOME=/home/arena

EXPOSE 8080

USER arena
WORKDIR /repo

# /healthz is the purpose-built probe: cheap, no git, no gh, and it 200s only
# when the server is actually serving. urllib raises on any non-2xx, so the
# container is marked unhealthy instead of flapping.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python3 -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('ARENA_PORT','8080'), timeout=4)"

# One entry point: the web UI. Open http://localhost:8080 after `docker run`.
#
# No VOLUME for /repo: a bind mount is a host decision. A VOLUME line would
# create an empty anonymous volume the first time someone forgets the mount.
ENTRYPOINT ["/usr/local/bin/arena-docker-entrypoint"]
CMD []
