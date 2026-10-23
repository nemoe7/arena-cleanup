# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-10-23

### Added

- The container log stamps every line in the zone of `TZ`. It names the start and the end of each job, each repo add and remove, and each failed request. `-v` adds every request and every engine line.
- A commit subject wraps to two lines, then an ellipsis. A tap on the row shows the whole subject.
- The PR check reads the version in `pyproject.toml` at the head and at the base branch. The head must be exactly one step above the base: the next patch, minor, or major.

### Changed

- The run card keeps the log of the latest run open under the phase list. The Show log toggle is gone, and Copy log is a glyph button with an accessible name.
- Icons follow three size tokens at every width. Inline glyphs are 14 px, buttons, phase rows, tree rows, and banners 16 px, and icon buttons 18 px. Most glyphs were 12 or 13 px.
- The arena row on a repo card is two lines at every width. The branch name sits on the first line, the ahead chip and the PR pill on the second. The dots before the name and in the PR pill are gone.
- The ahead chip shows the net count. That is its commits beyond the default branch, minus the default branch's commits beyond it. The chip hides below 1.

### Fixed

- A repeat add of a URL reuses the clone that already has that origin, `.git` or not. One repo keeps one card and one directory. A different repo with the same name still gets its own `-2` directory.

## [0.1.0] - 2026-10-22

### Added

- Web app, rewrite engine, Docker image, and test suite from the off-GitHub project.
- The CLI is one standard-library file, `arena-cleanup.py`, with the Windows launcher `arena-cleanup.cmd`. It runs on a PC with Python 3.11, `git`, and `gh`. The image runs the same file. It carries its own version, `pyproject.toml` carries the web app's, and a test keeps the two equal.
- uv-managed tool chain: `uv sync` installs Ruff, shfmt, pytest, and `git-filter-repo` from `uv.lock`.
- GitHub workflows: CI (lint, format, prose, Markdown, suite), the pull request contract, and an advisory container scan.
- Image publishing: a green CI run on `main` pushes `ghcr.io/nemoe7/arena-cleanup:latest` for amd64 and arm64, the only tag.
- `scripts/demo.py`: a throwaway fixture served by the UI for demos and the QA tools. It holds five repos, a stub `gh`, an identity, and a GPG key. Each repo has 14 commits on main and nine on the arena branch. In `infra-tools` main moved on by two commits after the session, and `data-pipeline` keeps two arena branches. The origins answer to `https://github.com/demo/<name>`, so the page shows live-looking remotes. The fixture clones them by URL under its data directory. The stub `gh` is signed in as the configured identity, the credential helper is set, and the host's tokens are gone.
- `docs/design.md`: the design record with the type ramp, spacing scale, breakpoints, and accepted decisions.
- Prose rules for comments, docstrings, and docs: sentences of 20 words or fewer, paragraphs of four sentences or fewer.
- `/api/access` storage rows that name their origin under `source`.
- UI type sizes from one ramp per width class, held in `--fs-*` tokens. Icons are Lucide glyphs inlined as SVG, with the ISC licence beside the page.
- A 360 px layout: the signing fields, commit metadata, and access labels stack. Create key is disabled while gpg is missing.
- The test suite as pytest under `tests/`: the engine, web app, and compose checks keep the bash fixtures. `uv run pytest` runs it, in CI too.
- The spacing audit as a Playwright test in `tests/e2e/`, run by the CI job with a cached Chromium. The browser walk `scripts/walk.py`, run by hand, saves its screenshots where you point it.
- A minimal README: install, use, settings, and development.
- An add bar that takes a GitHub page address: `github.com/owner/repo`, with or without `https://`, `.git`, or a page suffix.
- Cards and the repo title show the name only.
- Design boards in `docs/design/`, rendered by `scripts/design_boards.py` and embedded in `docs/design.md`.
- The repo card meta drops the tag count. It shows the branch and the tree state.
- Arena rows on the card and in the sidebar show `↑ N` with a tooltip. N counts the commits beyond the default branch.
- `run -a/--arena NAME` answers the arena branch menu without a prompt. The page shows that select, newest tip first, when a repo has two or more arena branches. The card button uses the newest.
- The repo sidebar is 320 px wide. It lists the commits below the repo facts and the arena rows. The HEAD block is gone. Below 900 px it stacks under the run card, and the commit list grows with the page.
- A shallow history: one Back leaves a sub-view, the next one leaves the page.
- A click on a sidebar arena row selects the arena branch the run pulls from. The Arena branch select and the row follow each other.
- The options card: one row per option, no hint texts, no task note. Checkboxes Dry Run, Ignore PR Checks, Keep Empty Commits, Update Tags (on by default), and Force Push replace the switches. Keep arena branch is gone. PR check timeout is a slider with ten stops and a readout. The page draws the checkboxes: a 16 px box, the accent fill, and a Lucide check. Above 1200 px the selects and Remove paths sit left, PR check timeout and the checkboxes right.
- A managed clone resets to origin before every run. The server fetches, checks out the default branch, resets hard, and drops local `arena/*` copies. The page has no Reset button, dirty chip, or On divergence control, and `--on-divergence` stays a CLI flag.
- The app copy says repo and repos.
- The claim rules come from the global git config keys `arena.claim-email` and `arena.claim-name`. The constants are the fallback. The container seeds the identity only while git config is empty.
- One Settings page behind the gear icon: Identity, GitHub access, Commit signing, and Claimed commits, then About.
- The page has three named breakpoints, 1200, 900, and 640 px. 1200 folds the options to one column, 900 stacks the sidebar, 640 starts the phone ramp.
- Six buttons carry a Lucide glyph. Reload is `refresh-cw` alone with an accessible name. Re-check and Retry lead with `refresh-cw`, Copy log and Copy public key with `copy`, Browse with `folder-tree`. Show log carries the fold caret.
- The page matches its design record after an audit. Every banner leads with its glyph. Pointer targets are at least 24 px: Browse, the chip X, the tree select, the check rows, and the slider. The version chip weighs 520 and bold runs 600. A dead brand size rule goes, and two paddings sit on the scale.
- The repo wireframe board grows its blocks with their text, and its marks are glyphs instead of font symbols.
- The Docker workflow starts only for CI on main, so other branches no longer record a skipped run.
- The test suite runs on every CPU core through pytest-xdist. Each file stays on one worker, so the web app story in `tests/test_ui.py` keeps its order.
- The config files follow the repo template. Git normalizes line endings to LF, and GitHub prefills a pull request body with its three sections. The project metadata names the README and the licence.
- `AGENTS.md` carries the shared agent rules of the repo template, with the nuu and nemoizer sections below them.
- Log rows show the clock of the browser. The engine stamps each line in the server zone.
- Remove on a card deletes its URL clone from the volume. A path repo is only forgotten.
- `POST /api/repos/<id>/reset`: fetch, check out the default branch, and reset it hard. Untracked files stay.
- The repo page runs the full flow only. The Rewrite locally switch is gone, and `strip` stays a CLI command.
- The card Remove X sits top right as a bare glyph. A red frame comes on hover, on press, and while armed.
- The primary button reads Clean & Push on the card, the run card, and the phone bar.
- The options card folds from its head. Closed, the head shows the branch pill and what differs from the defaults.
- Target branch lists the default branch first and never an `arena/*` branch. The page API answers 400 for one.
- Browse under Remove paths opens the HEAD tree of the clone, one level per request. A click on a row or its plus adds the path chip. `GET /api/repos/<id>/tree?path=` serves the level.
- The demo histories keep tests under `tests/` and the workflow under `.github/workflows/`, so the tree has folders to open.
- The tab title reads `arena-cleanup` on the dashboard and `arena-cleanup | <page>` elsewhere: the repo name, Settings, or Offline. One setter runs on every view change.
