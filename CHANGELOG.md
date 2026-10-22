# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- uv-managed tool chain: `uv sync` installs Ruff, shfmt, and `git-filter-repo` from `uv.lock`.
- GitHub workflows: CI (lint, format, Markdown, suite), the pull request contract, and an advisory container scan.
- Image publishing: a green CI run on `main` pushes `ghcr.io/nemoe7/arena-cleanup:latest` for amd64 and arm64, the only tag.
- `scripts/demo.py`: a throwaway fixture served by the UI for demos and the QA tools. It holds three repositories, a stub `gh`, an identity, and a GPG key.

### Changed

- Comments, docstrings, and docs follow the nemoizer rules. Sentences stay at 20 words or fewer, paragraphs at four sentences or fewer.
- `/api/access` storage rows name their origin under `source` instead of `kind`. <!-- nonemo: P001 -->

## [0.1.0] - 2026-10-22

### Added

- Web app, rewrite engine, Docker image, and test suite from the off-GitHub project.
- One version source: `pyproject.toml`, read by the engine and the UI.
