# Changelog

<!-- nonemo: NMO901; nonemo: STE901; nonemo: STE902 -->

This file documents all notable changes to the UI, the web app in `ui/`.
The engine, `arena-cleanup.py`, carries its own number and its own file,
`CHANGELOG-engine.md`, from 0.3.0 on. Up to 0.3.0 both parts shared this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.3] - 2026-10-24

### Fixed

- The paddings and gaps the nuu audit found off the 4 px scale.
  - The icon buttons and the path input drop the browser default padding.
  - Back pads 12 px, the phase rows and Browse gap 8 px, the step and log rows 12 px.
  - The brand link pads 8 px.
- On a phone the PR pill and the repo name hit 44 px tall through an unseen box above and below.
  - The claim inputs are 44 px tall there too.
- Every commit row of a page enters within one 120 ms spread. Before, only the first twelve rows animated, and the rest popped in solid next to still transparent rows.
- Below 640 px a phase modal step row shows the stamp and the duration on one line, then the text at full width.

## [0.3.2] - 2026-10-24

### Added

- A motion set on a vendored GSAP 3.15.0.
  - A view fades in.
  - The first cards, the first commits, and a dialog fade in with an 8 px rise, 180 ms on one curve.
  - A reduced-motion preference paints at once.
  - The licence sits in `ui/static/LICENSE-gsap.txt`.
- Each run phase row opens a modal with its detail.
  - Prepare, PR checks, and Clean up list their steps with a clock stamp and the time each took.
  - Rewrite and sign lists the commits after the rewrite under the engine's counts.
  - Push shows the ref, the move from the old hash to the new one, the lease, the moved tags, and a GitHub link.
  - The last row reads Clean up.
- A loading bar under the header follows the repo fetch: the server counts
  two steps per repo, the fetch and the status, and `GET /api/progress`
  reports them. The Reload glyph spins while the page follows a fetch.
- A PR checks pill opens a modal with the checks of that PR: one row per
  check with its state, a run link when GitHub names one, and the PR link.
  The sidebar arena rows carry a check button for the same modal, and
  `pr_checks` adds the `checks` list next to the counts.

### Changed

- The How git reaches GitHub fold is gone. The GitHub card shows the
  credential helper, the ssh keys, and the helper warning with Configure under
  the sign-in state, and the README carries the SSH mount hint.
- Every card action sits bottom right in a card foot: the run button under
  the options, both Save buttons, Re-check, Sign in, Configure, Create key at
  its natural width, and Open GitHub keys.
- Clean & Push rests when no arena branch is ahead on origin: the dashboard
  button, the run button, and the phone bar grey out with the tooltip nothing
  to clean or push. A named target branch keeps the run button live.

### Fixed

- A clone refused while a reload of the list is in flight leaves no pending
  card behind. The reload reads the pending cards after its wait, not before.
- The run phases measure one contiguous timeline.
  - A line names the current phase or a later one, never an earlier one, and the next phase starts where the last one ends.
  - A stale branch deleted in Prepare no longer starts Finish, and the commit scan no longer stretches Prepare.
- The ahead chip pads the arrow ink and the count the same: the icon moves
  2 px in and the gap narrows to 6 px, so the chip reads centred.
- A reload at `#/settings` or in a repo view paints that screen first. The
  dashboard no longer shows while the environment and the repos load.

## [0.3.1] - 2026-10-24

### Changed

- The three breakpoints read 75em, 56.25em, and 40em instead of 1200, 900,
  and 640 px, so the layouts follow the reader's browser font size. Same
  widths at the 16 px default.
- Four values sit on the 4 px scale: fields pad 12 px, the pill gap is 8 px,
  the phone keeps the 16 px page padding, and the phone title reads 20 px.
  Pill radii read 1000 px, the same shape.
- The UI and the engine carry separate versions: `pyproject.toml` holds the
  UI, `arena-cleanup.py` the engine. The version check asks for one step in
  a part whose files changed and none in the other, so a docs-only change
  needs no bump.
- The PR pill and the sidebar dot paint running checks amber, the GitHub
  pending colour, instead of blue. A PR without checks gets a grey dot.
- A sidebar arena row takes two lines: the dot and the name, then the ahead
  count and the PR meta under the name, as the cards do.
- List edits show before the reply: the arena row leaves on Delete, the card
  leaves on Remove, and Add puts a pending card first. A refused call puts
  the row back with the error, and a lost connection sends the write once
  more.
- The sidebar Delete button stays a 32 px square on a desktop instead of
  stretching to the height of its two-line row.
- The toast and the log's jump button lose their drop shadows. Every surface
  is flat, the nuu rule, and the focus rings stay.
- Every transition runs 160 ms on one curve, from two tokens, instead of
  120 or 180 ms on the browser default.
- The delete modal has an x top right that closes it like Cancel.
- Hover tints apply only with a pointer, under `@media (hover: hover)`, so a
  tap on a touch screen leaves no stuck hover state. Focus and active stay.
- Every colour below `:root` is a role token. The pills and the banners share
  one text, line, and tint per tone, so their tints differ by at most two per
  cent from before.

## [0.3.0] - 2026-10-23

### Added

- The repo view deletes an arena branch on origin: a trash control on each
  sidebar row, a modal that names the branch first, and
  `POST /api/repos/<id>/arena/delete` behind it.
- The dashboard sorts the repos: newest arena activity first, name A to Z,
  or PR state with failures first. The select sits beside Reload and the
  browser keeps the choice.
- The commit list pages 30 at a time.
  - A scroll near the end loads the older page through a `before` cursor on the commits API, which answers `next`.
  - Reload restarts at the first page.
- The commit list and the log fade 12 px at a scrolled edge, the nuu
  scroll-edge fade. It needs scroll-driven animations and no reduced-motion
  preference, and a panel that does not scroll stays unmasked.

### Changed

- The settings page is two columns above 1200 px: Identity, Claimed commits,
  and About left, GitHub and the keys right. How git reaches GitHub and About
  fold at every width and open on a click.
- The commit hint reads the commit count alone, with thousands separators,
  in place of `shown of total on branch`.
- Every Clean & Push button carries the broom glyph before its words, and its
  sparkles appear on hover and focus.
- A dashboard card puts Clean & Push bottom right and drops the branch chip.
  - The icon, the name, and Remove share one centre line on top.
  - The rows keep the chip.
- Above 1200 px the dashboard shows one full-width row per repo.
  - The row holds the name, the branch, the arena rows across the free width, then Clean and Remove at the right edge.
  - An arena row is one line there and the rows stack.
  - At 1200 px and below the repos stay cards with two-line arena rows.
- The Remove button carries the trash glyph in place of the X.
- Human-facing text says push, not publish, and PR, not pull request: the
  page, the engine log lines, the CLI help, the README, and the design record.
  Identifiers, API fields, and past entries keep their words.
- The Force Push option reads No lease.
  - Checked, or with `-f`, the run pushes with `git push --force` and no lease, so it lands even when the default branch moved during the run.
  - The log says `pushing (with lease)` or `force-pushing (no lease)`, and a dry run says what a real run would do.

### Removed

- The Keep Empty Commits option, its `keep_empty` run field, and the CLI flag
  `-E/--keep-empty`. Commits that only touched removed paths are always dropped.

## [0.2.5] - 2026-10-23

### Changed

- The app icon and the brand mark are the Lucide broom-sparkles glyph in the
  accent colour. `scripts/app_icon.py` draws the favicon and the PWA pictures.

## [0.2.4] - 2026-10-23

### Added

- The commit rows show the author's GitHub picture. The server keeps one picture
  per address for 30 days after its last use and prunes the rest.

### Changed

- The latest-run lookup of a repo without runs answers 204 with no body, so the
  browser console stays clean on a fresh repo view.
- The phase rows of the run card show counts instead of hint texts: the checks
  passed of the total, the commits collected, signing, and signed, and the tags
  moving, pushing, and pushed. The Publish row is named Push.

## [0.2.3] - 2026-10-23

### Changed

- CI keys the Chromium cache on the Playwright version, so a release bump keeps
  the cache.

## [0.2.2] - 2026-10-23

### Fixed

- The run card and the options card of the repo view end on one line. The first option row sits right under the card head like the phase rows, and the rule under the last option row is gone.

## [0.2.1] - 2026-10-23

### Changed

- The repo view puts the run card left and the options card right, with the log below both at full width.
  - The main column pins to the window.
  - The log takes the height that is left, down to a 160 px floor, so only the log scrolls.
  - At 1200 px and below the two cards stack, options first.
- Clean & Push and Cancel are one button with two states, in the options card head.
  - It reads Cancel while a run is live.
  - The options card no longer folds, and the options sit in one column at every width.
- The primary button is flat. Its inset top highlight and its drop shadow, which read as a bevel, are gone.
- The clock column of the log rows takes the dim grey of the level column, 5.1:1 on the card. Before, it read at 2.55:1.

### Fixed

- The server runs one fetch of every origin at a time.
  - The server skips a fetch within ten seconds of the last one, except from the Reload button.
  - A Reload during a running fetch waits for it and skips its own.
  - Each fetch swaps fresh statuses into the cache instead of clearing it.
  - A dashboard that asks in the meantime gets cards instead of a gap.
- The dashboard shows a Loading repos line until the first answer from the server. Before, the page opened on an empty space.
- The repo view no longer scrolls the page on a desktop window. The cards and a 340 px log were taller than a 775 px window.
- The PR pill counts the checks the way the engine reads them.
  - One entry per check name, and a pass wins over a superseded failed or cancelled attempt.
  - Before, a cancelled older run of a check kept the pill red while the run passed.

## [0.2.0] - 2026-10-23

### Added

- The container log stamps every line in the zone of `TZ`.
  - It names the start and the end of each job, each repo add and remove, and each failed request.
  - `-v` adds every request and every engine line.
- A commit subject wraps to two lines, then an ellipsis. A tap on the row shows the whole subject.
- The repo view shows the latest run again on every open.
  - A live run streams on.
  - A finished run comes back with its log, phases, and status, also after a server restart.
  - The server saves the finished run of each repo under `ARENA_DATA/jobs/`.
- A Reload button on the dashboard fetches every repo now. The server also fetches each repo at the top of every clock minute, and a page load fetches once.
- The PR check reads the version in `pyproject.toml` at the head and at the base branch. The head must be exactly one step above the base: the next patch, minor, or major.

### Changed

- The run card keeps the log of the latest run open under the phase list. The Show log toggle is gone, and Copy log is a glyph button with an accessible name.
- Icons follow three size tokens at every width.
  - Inline glyphs are 14 px, buttons, phase rows, tree rows, and banners 16 px, and icon buttons 18 px.
  - Most glyphs were 12 or 13 px.
- The arena row on a repo card is two lines at every width.
  - The branch name sits on the first line, the ahead chip and the PR pill on the second.
  - The dots before the name and in the PR pill are gone.
- The ahead chip shows the net count.
  - That is its commits beyond the default branch, minus the default branch's commits beyond it.
  - The chip hides below 1.
- On a repo card the name is the button that opens the repo. The card has no button role any more, so the controls inside it stand on their own for assistive technology.
- Monaspace Neon replaces JetBrains Mono for paths, hashes, commands, and the log. The page preloads both fonts and paints them with block, and each has a metric-matched local fallback face.

### Fixed

- A repeat add of a URL reuses the clone that already has that origin, `.git` or not.
  - One repo keeps one card and one directory.
  - A different repo with the same name still gets its own `-2` directory.

## [0.1.0] - 2026-10-22

### Added

- Web app, rewrite engine, Docker image, and test suite from the off-GitHub project.
- The CLI is one standard-library file, `arena-cleanup.py`, with the Windows launcher `arena-cleanup.cmd`.
  - It runs on a PC with Python 3.11, `git`, and `gh`.
  - The image runs the same file.
  - It carries its own version, `pyproject.toml` carries the web app's, and a test keeps the two equal.
- uv-managed tool chain: `uv sync` installs Ruff, shfmt, pytest, and `git-filter-repo` from `uv.lock`.
- GitHub workflows: CI (lint, format, prose, Markdown, suite), the pull request contract, and an advisory container scan.
- Image publishing: a green CI run on `main` pushes `ghcr.io/nemoe7/arena-cleanup:latest` for amd64 and arm64, the only tag.
- `scripts/demo.py`: a throwaway fixture served by the UI for demos and the QA tools.
  - It holds five repos, a stub `gh`, an identity, and a GPG key.
  - Each repo has 14 commits on main and nine on the arena branch.
  - In `infra-tools` main moved on by two commits after the session, and `data-pipeline` keeps two arena branches.
  - The origins answer to `https://github.com/demo/<name>`, so the page shows live-looking remotes.
  - The fixture clones them by URL under its data directory.
  - The stub `gh` is signed in as the configured identity, the credential helper is set, and the host's tokens are gone.
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
- `run -a/--arena NAME` answers the arena branch menu without a prompt.
  - The page shows that select, newest tip first, when a repo has two or more arena branches.
  - The card button uses the newest.
- The repo sidebar is 320 px wide.
  - It lists the commits below the repo facts and the arena rows.
  - The HEAD block is gone.
  - Below 900 px it stacks under the run card, and the commit list grows with the page.
- A shallow history: one Back leaves a sub-view, the next one leaves the page.
- A click on a sidebar arena row selects the arena branch the run pulls from. The Arena branch select and the row follow each other.
- The options card: one row per option, no hint texts, no task note.
  - Checkboxes Dry Run, Ignore PR Checks, Keep Empty Commits, Update Tags (on by default), and Force Push replace the switches.
  - Keep arena branch is gone.
  - PR check timeout is a slider with ten stops and a readout.
  - The page draws the checkboxes: a 16 px box, the accent fill, and a Lucide check.
  - Above 1200 px the selects and Remove paths sit left, PR check timeout and the checkboxes right.
- A managed clone resets to origin before every run.
  - The server fetches, checks out the default branch, resets hard, and drops local `arena/*` copies.
  - The page has no Reset button, dirty chip, or On divergence control, and `--on-divergence` stays a CLI flag.
- The app copy says repo and repos.
- The claim rules come from the global git config keys `arena.claim-email` and `arena.claim-name`.
  - The constants are the fallback.
  - The container seeds the identity only while git config is empty.
- One Settings page behind the gear icon: Identity, GitHub access, Commit signing, and Claimed commits, then About.
- The page has three named breakpoints, 1200, 900, and 640 px. 1200 folds the options to one column, 900 stacks the sidebar, 640 starts the phone ramp.
- Six buttons carry a Lucide glyph.
  - Reload is `refresh-cw` alone with an accessible name.
  - Re-check and Retry lead with `refresh-cw`, Copy log and Copy public key with `copy`, Browse with `folder-tree`.
  - Show log carries the fold caret.
- The page matches its design record after an audit.
  - Every banner leads with its glyph.
  - Pointer targets are at least 24 px: Browse, the chip X, the tree select, the check rows, and the slider.
  - The version chip weighs 520 and bold runs 600.
  - A dead brand size rule goes, and two paddings sit on the scale.
- The repo wireframe board grows its blocks with their text, and its marks are glyphs instead of font symbols.
- The Docker workflow starts only for CI on main, so other branches no longer record a skipped run.
- The test suite runs on every CPU core through pytest-xdist. Each file stays on one worker, so the web app story in `tests/test_ui.py` keeps its order.
- The config files follow the repo template.
  - Git normalizes line endings to LF, and GitHub prefills a pull request body with its three sections.
  - The project metadata names the README and the licence.
- `AGENTS.md` carries the shared agent rules of the repo template, with the nuu and nemoizer sections below them.
- Log rows show the clock of the browser. The engine stamps each line in the server zone.
- Remove on a card deletes its URL clone from the volume. A path repo only leaves the list.
- `POST /api/repos/<id>/reset`: fetch, check out the default branch, and reset it hard. Untracked files stay.
- The repo page runs the full flow only. The Rewrite locally switch is gone, and `strip` stays a CLI command.
- The card Remove X sits top right as a bare glyph. A red frame comes on hover, on press, and while armed.
- The primary button reads Clean & Push on the card, the run card, and the phone bar.
- The options card folds from its head. Closed, the head shows the branch pill and what differs from the defaults.
- Target branch lists the default branch first and never an `arena/*` branch. The page API answers 400 for one.
- Browse under Remove paths opens the HEAD tree of the clone, one level per request.
  - A click on a row or its plus adds the path chip.
  - `GET /api/repos/<id>/tree?path=` serves the level.
- The demo histories keep tests under `tests/` and the workflow under `.github/workflows/`, so the tree has folders to open.
- The tab title reads `arena-cleanup` on the dashboard and `arena-cleanup | <page>` elsewhere: the repo name, Settings, or Offline. One setter runs on every view change.
