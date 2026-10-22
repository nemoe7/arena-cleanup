# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- uv-managed tool chain: `uv sync` installs Ruff, shfmt, pytest, and `git-filter-repo` from `uv.lock`.
- GitHub workflows: CI (lint, format, Markdown, suite), the pull request contract, and an advisory container scan.
- Image publishing: a green CI run on `main` pushes `ghcr.io/nemoe7/arena-cleanup:latest` for amd64 and arm64, the only tag.
- `scripts/demo.py`: a throwaway fixture served by the UI for demos and the QA tools. It holds three repositories, a stub `gh`, an identity, and a GPG key.
- `docs/design.md`: the design record with the type ramp, spacing scale, breakpoints, and accepted decisions.

### Changed

- Comments, docstrings, and docs follow the nemoizer rules. Sentences stay at 20 words or fewer, paragraphs at four sentences or fewer.
- `/api/access` storage rows name their origin under `source` instead of `kind`. <!-- nonemo: P001 -->
- UI type sizes come from one ramp per width class, held in `--fs-*` tokens. Inline SVG icons replace the text glyphs.
- At 360 px the signing fields, commit metadata, and access labels stack. Create key is disabled while gpg is missing.
- The test suite is pytest under `tests/`: the engine, web app, and compose checks keep the bash fixtures. `uv run pytest` runs it, in CI too.
- The spacing audit is a Playwright test in `tests/e2e/`; a second CI job installs Chromium for it. The browser walk is `scripts/walk.py`, run by hand; it saves its screenshots where you point it.
- The README is cut to the essentials: install, use, settings, and development. The four extra UI screenshots are gone; the dashboard one is fresh.
- The checks pill in the arena row is the link on its own. The external-link icon beside it is gone.

### Removed

- `run-tests.sh` and `tools/`; `tests/` and `scripts/walk.py` replace them.

## [0.1.0] - 2026-10-22

### Added

- Web app, rewrite engine, Docker image, and test suite from the off-GitHub project.
- One version source: `pyproject.toml`, read by the engine and the UI.
