# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-22

### Added

- Web app, rewrite engine, Docker image, and test suite from the off-GitHub project.
- One version source: `pyproject.toml`, read by the engine and the UI.
- uv-managed tool chain: `uv sync` installs Ruff, shfmt, pytest, and `git-filter-repo` from `uv.lock`.
- GitHub workflows: CI (lint, format, Markdown, suite), the pull request contract, and an advisory container scan.
- Image publishing: a green CI run on `main` pushes `ghcr.io/nemoe7/arena-cleanup:latest` for amd64 and arm64, the only tag.
- `scripts/demo.py`: a throwaway fixture served by the UI for demos and the QA tools. It holds five repositories, a stub `gh`, an identity, and a GPG key. Each repository has 14 commits on main and nine on the arena branch. In `infra-tools` main moved on by two commits after the session, and `data-pipeline` keeps two arena branches. The origins answer to `https://github.com/demo/<name>`, so the page shows live-looking remotes. The fixture clones them by URL under its data directory. The stub `gh` is signed in as the configured identity, the credential helper is set, and the host's tokens are gone.
- `docs/design.md`: the design record with the type ramp, spacing scale, breakpoints, and accepted decisions.
- Prose rules for comments, docstrings, and docs: sentences of 20 words or fewer, paragraphs of four sentences or fewer.
- `/api/access` storage rows that name their origin under `source`.
- UI type sizes from one ramp per width class, held in `--fs-*` tokens. Icons are Lucide glyphs inlined as SVG, with the ISC licence beside the page.
- A 360 px layout: the signing fields, commit metadata, and access labels stack. Create key is disabled while gpg is missing.
- The test suite as pytest under `tests/`: the engine, web app, and compose checks keep the bash fixtures. `uv run pytest` runs it, in CI too.
- The spacing audit as a Playwright test in `tests/e2e/`, run by the CI job with a cached Chromium. The browser walk `scripts/walk.py`, run by hand, saves its screenshots where you point it.
- A minimal README: install, use, settings, and development.
- An add bar that takes a GitHub page address: `github.com/owner/repo`, with or without `https://`, `.git`, or a page suffix.
- Cards and the repository title show the name only.
- Design boards in `docs/design/`, rendered by `scripts/design_boards.py` and embedded in `docs/design.md`.
- The repository card meta drops the tag count; it shows the branch, the tree state, and the drift.
- A shallow history: one Back leaves a sub-view, the next one leaves the page.
- The card shows `N uncommitted` only when the clone is dirty.
- The app copy says repo and repos.
- The claim rules come from the global git config keys `arena.claim-email` and `arena.claim-name`; the constants are the fallback. The container seeds the identity only while git config is empty.
- One Settings page behind the gear icon: Identity, GitHub access, Commit signing, and Claimed commits, then About.
- The options card keeps two columns above 980 px; four columns overflowed between 981 and 1179 px. The divergence control wraps whole buttons, not words.
- Log rows show the clock of the browser. The engine stamps each line in the server zone.
- Remove on a card deletes its URL clone from the volume; a path repo is only forgotten.
- Reset to origin in the repository sidebar: fetch, check out the default branch, and reset it hard. Untracked files stay.
