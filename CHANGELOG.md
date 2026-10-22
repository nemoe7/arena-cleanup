# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- uv-managed tool chain: `uv sync` installs Ruff, shfmt, and `git-filter-repo` from `uv.lock`.

## [0.1.0] - 2026-10-22

### Added

- Web app, rewrite engine, Docker image, and test suite from the off-GitHub project.
- One version source: `pyproject.toml`, read by the engine and the UI.
