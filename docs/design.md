# Design record

The one design record for the arena-cleanup web app. The sections follow the nemo-ui-ux skill template. The token source is the `:root` block in `ui/static/index.html`.

## Purpose and status

- Goal: clean an arena branch (rewrite, sign, publish) from a browser, on a phone or a desktop.
- Scope: the dashboard, the repo view, and the settings view.
- Constraints: one HTML file, no build step, and a dark theme only. Fonts and icons ship with the page, so nothing loads from the network.
- Acceptance checks: the pytest suite in `tests/`, screenshots at 1280 and 360 px, and the nemo-ui-ux measure reports.
- Design status: accepted for the four views. The audit findings of 2026-10-22 are fixed.

## Users, tasks, and language

- User group: one developer who owns the repos and the GitHub account. No research beyond that use.
- Primary tasks: add a repo, run a cleanup, read the log, and keep the settings right. Settings: GitHub access, signing, identity, and the claim rules.
- Repo: a clone the server registered. Identifier: the server-minted `id`. The card shows `name` only.
- Arena branch: a branch under the `arena/` prefix with its pull request and check count.
- Run: one engine execution with five phases: Prepare, PR checks, Rewrite and sign, Publish, Finish.

## Journeys and information architecture

- Entry: the dashboard at `/`. The header holds the brand, the tool dots, and one icon button (Settings).
- Dashboard to repo: a click on the card or Enter on a focused card. The name underlines on hover. Back: the All repos button.
- Settings opens from the header, and Back returns to the previous view. The old `#/access` and `#/signing` links land on the matching cards.
- Recovery: a failed run keeps its log open, and a failed load shows a banner with the error text. The service worker caches the shell only, never server state.

## Screens and states

- Dashboard: add bar, repo cards. Empty: a hint with the add command. Error: a banner above the cards. A card shows the branch. Each arena row carries `↑ N`, the commits that branch holds beyond `origin/<default>`, with a tooltip. The Remove X sits top right as a bare glyph. A red frame comes on hover, on press, and while armed.
- Repo: a 320 px sidebar, options card, run card with the phase list and log. The options card folds from its head. Closed, the head shows the branch pill and what differs from the defaults. Each option is one row: label, control, and a trailing action or readout. No hint texts. Dry Run, Ignore PR Checks, Keep Empty Commits, Update Tags (checked by default), and Force Push are checkboxes. PR check timeout is a slider with the number beside it. It snaps to 0, 5, 10, 15, 20, 30, 45, 60, 90, or 120 minutes. Target branch lists the default branch first and never an `arena/*` branch. Arena branch appears with two or more arena branches, newest tip first. The chosen one goes to the run as `--arena`. The sidebar holds the repo facts and the arena rows on top. The commit list fills the rest and scrolls on its own. Each row shows hash, subject, author, and date. Reload sits in its label. Each arena row shows the PR state and is a button that selects the branch to pull from. The page runs the full flow only. `strip` is a CLI command. Browse under Remove paths opens the HEAD tree of the clone, one level per request. A click on a row or its plus adds the chip. Log rows show the clock of the browser. Remove on a card arms on the first click and deletes the URL clone on the second. States: idle, running, done, failed, cancelled. A managed clone goes back to origin before every run. The server fetches, checks out the default branch, resets hard, and drops local `arena/*` copies.
- Settings: Identity (name, email, Save), GitHub sign-in and credential helper, signing cards, Claimed commits (two chip lists, Save). Below: About. Signing cards: gpg banner when gpg is missing, key list, create card, GitHub key steps. Disabled: Create key while gpg is missing. Error: the banner names the failed check. Each card loads on its own.
- Offline: the service worker serves the shell. Data requests fail with the normal error banner.
- Loading and permission states: not run as separate checks.

## Design system and tokens

### Colour

- Roles: `bg`, `surface`, `surface-2`, `surface-3`, `line`, `line-2`, `text`, `muted`, `dim`, `accent`, `accent-hi`, `accent-soft`, `ok`, `warn`, `err`, `info`.
- One dark theme, `color-scheme: dark`. Contrast checks: not run.

### Type

- Inter (variable) for text, JetBrains Mono for paths, hashes, and commands. Both ship as woff2 under `ui/static/fonts/`.
- Desktop ramp: `--fs-1` 12 px for metadata and mono details, `--fs-2` 13 px for controls and labels. `--fs-3` 14 px for body, names, and buttons, `--fs-4` 16 px for a view title, `--fs-5` 20 px for the page title.
- Phone ramp at 720 px and below: body 12 to 15 px, fields 16 px, and title 19 px. The 16 px fields keep iOS from zooming.
- Weights: 400, 520 to 640 for labels and names, 600 for headings.

### Icons

- Lucide 1.61.0, vendored one glyph at a time into the `ICONS` map in `index.html`. Each glyph keeps its 24 px grid, drawn at 1 em and stroked at 2 in the text color.
- Names in use: arrow-left, arrow-up, arrow-down, chevron-right, check, x, triangle-alert, minus, circle-small, loader-circle, git-branch, key-round, and shield-check.
- Static slots carry `data-icon="<name>"` and are filled at boot. The brand mark is the project logo, not a glyph.
- No text glyphs stand in for icons. The licence sits beside the page in `ui/static/LICENSE-lucide.txt`.

### Layout

- Spacing scale: 2, 4, 6, 8, 10, 12, 16, 20, 24, and 32 px, with 1 px for borders.
- Page padding `--pad`: 20 px, 16 px at 980 px and below, 14 px at 720 px and below.
- Breakpoints: the options sit in two columns at every width above 980 px. 980 px keeps one column and stacks the sidebar below the run card. 720 px switches to the phone ramp, 44 px targets, and stacked rows.
- Radius `--r` 10 px for cards, 8 px for buttons and fields, 999 px for pills.

### Theme and motion

- Transitions of 120 to 180 ms on transform, opacity, border, and background. `prefers-reduced-motion` stops them.

## Components and contracts

- `btn`: 34 px high, 12 px side padding, 8 px radius, and 44 px high on a phone. Variants: `primary`, `ghost`, and `icon-btn`.
- `pill`: dot and word, 999 px radius, `ok`, `warn`, `mono` variants.
- `commit`: grid `auto minmax(0, 1fr)`, the subject truncated by an ellipsis, the metadata on a second row.
- `row-btn.select`: a sidebar arena row that is a button with `aria-pressed`. The selected row carries a 2 px accent bar and the text colour. The name reads `Pull from <branch>`. Rows and the timeout slider are 44 px high on a phone.
- `opt.row`: a grid of three columns, `128px minmax(0, 1fr) auto`, for the label, the control, and the trailing Browse or slider readout. `check`: a label with a drawn checkbox. The box is 16 px with a 4 px radius and the surface-2 fill. Checked, it takes the accent fill and a white Lucide check. `danger` fills a checked destructive option with the warn colour and a dark check. On a phone the checkboxes form a grid with 160 px columns. Browse and the fold head are 44 px high there.
- `repo-card`: a flex column. The actions sit at the bottom, so the buttons line up across a grid row.
- `sign-row`: label column of 120 px and a value column. On a phone the label takes a full row.
- `sign-fields`: name and e-mail side by side, one column on a phone.
- `banner`: `err`, `warn`, `ok` variants with an icon and one sentence of action.
- `fold-head`: a card head that is one button with `aria-expanded` and `aria-controls`. The caret turns. The pill and the summary show only while closed.
- `tree`: the path selector. Rows are `treeitem`s with `aria-level`. A folder row carries `aria-expanded` and loads its children on the first open. The trailing `tree-select` button toggles the path and reports `aria-pressed`. Rows and select buttons grow to 44 px on a phone.

## Accessibility and inclusion

- Target: WCAG 2.2 AA for keyboard use and names. Applied so far: a skip link, `aria-label` on icon buttons, `role="status"` for the run state, and focus rings. Targets are 44 px on a phone.
- Test methods: the browser walk in `scripts/walk.py` (keyboard and names) and the measure reports (target sizes).
- Not run: screen reader sessions, contrast measurement.

## Content and assets

- Copy follows ASD-STE100: short sentences, one action per banner, no jargon beyond git and GitHub terms.
- Locale: English only. Dates use the browser locale.
- Fonts: Inter and JetBrains Mono, SIL Open Font License 1.1, see `ui/static/fonts/LICENSE.txt`. Icons: Lucide, ISC, see `ui/static/LICENSE-lucide.txt`.

## Behavior and data

- The repo registry and settings live on the server under `ARENA_DATA`. The page keeps no state beyond the open view.
- Defaults: PR check timeout 15 minutes, dry run off.
- Validation: the add bar accepts a clone URL, a GitHub page address, or a path. The server answers errors as text the banner shows.
- Retries: none automatic. Re-check and Reload buttons repeat a read.

## Evidence and handoff

- 2026-10-22 audit, before the fixes: nine font sizes at 1280 px and six at 360 px. The signing fields, commit rows, and access rows broke at 360 px. Create key stayed enabled without gpg, and icons were text glyphs.
- 2026-10-22 after the fixes: screenshots of the four views at 1280 and 360 px, plus measure reports. They show five sizes at 1280 px, stacked rows at 360 px, and inline SVG icons. The 8 px scale check still reports the 6, 10, and 12 px steps. See the decision below.
- Readiness: implemented. The spacing audit runs in `tests/e2e/`, the walk from `scripts/walk.py`.
- Boards: `uv run scripts/design_boards.py` renders the seven boards below into `docs/design/` from the live stylesheet and the demo fixture. Run it again after a token or component change.

### Boards

![Lay of the land: the three views and the moves between them](design/flow.png)

![Repo view: deep-dive wireframe and key actions](design/wireframe-repo.png)

![Example views: default, signed out, after a run, settings](design/views.png)

![Component states: run status, phase rows, arena row pills](design/states.png)

![Global components: buttons, pills, fields, checkboxes, banners, cards](design/components.png)

![Style guide: type ramp, colour roles, surfaces, radius, spacing, icons](design/style.png)

![Do and do not: spacing, type, icons, phone width, banners, honest pills](design/do-dont.png)

## Decisions and history

- Accepted 2026-10-22: one type ramp per width class, held in `--fs-*` tokens, instead of the nine ad hoc sizes.
- Accepted 2026-10-22: inline SVG icons, no icon font, and no text glyphs. Later that day the hand-drawn paths gave way to Lucide glyphs, as the house clause asks.
- Accepted 2026-10-22: the even spacing scale with 1 px borders stays. The 8 px house scale is not adopted, because the dense rows need 6 and 10 px steps.
- Accepted 2026-10-22: two breakpoints at 980 and 720 px. 1180 px is the content width, not a breakpoint. Four option columns were dropped, because the divergence control overflowed between 981 and 1179 px.
- Accepted 2026-10-22: in a narrow cell a segmented control wraps whole buttons onto a second row, never words.
- Accepted 2026-10-22: a shallow history. The dashboard is the root entry and a sub-view is at most one entry deep. One Back leaves a sub-view, the next one leaves the page.
- Accepted 2026-10-22: no command switch on the repo page. A local rewrite without a push is a terminal task, so `strip` lives in the CLI alone.
- Accepted 2026-10-22: the whole options card folds, not the Target branch row alone. The select names the default branch first, keeps the empty value, and lists no `arena/*` branch. The server refuses one too.
- Accepted 2026-10-22: with two or more arena branches the page selects one, newest tip first, in the options card. The engine gained `--arena NAME` for it and keeps the full flow. The page never passes `-b arena/*`.
- Accepted 2026-10-22: the sidebar grows to 320 px. The commit list sits below the repo facts and the arena rows. The HEAD block goes. The hash leads each commit row. Below 980 px the sidebar stacks under the run card instead of hiding. The commit list then grows with the page: one scroll per screen.
- Accepted 2026-10-22: a click on a sidebar arena row selects the arena branch the run pulls from. The Arena branch select follows the row and the row follows the select. The marked row never sets the target branch. With one arena branch the row only shows which branch that is.
- Accepted 2026-10-22: the options card loses its hint texts and the task note above it. Each option is one row. The switches become checkboxes with Title Case labels. Update Tags is the positive form of `--no-tags`. Keep arena branch goes. The reset before every run drops local copies, so a kept branch never reaches the next run. The timeout is a slider with ten stops and a readout.
- Accepted 2026-10-22: a managed clone holds nothing of its own. The server resets it to origin before every run and drops local `arena/*` copies. The page loses the Reset button, the dirty chip, and On divergence. `--on-divergence` stays a CLI flag.
- Accepted 2026-10-22: the card and the sidebar show how far each arena branch is ahead of the default branch. The clone's own drift stays out of sight. Nobody commits in the container, and the engine handles that divergence itself.
- Accepted 2026-10-22: the primary button reads Clean & Push. The phase list keeps Publish for the push, tags, and cleanup step.
- Accepted 2026-10-22: a tree selector for Remove paths. It reads `git ls-tree` of HEAD in the clone, so it works for path repos and never calls GitHub. File contents stay out. A path only old commits carried stays a typed chip.
- Accepted 2026-10-23: the page draws the checkboxes. `appearance: none` drops the browser box, so the boxes match the select and the fields in every browser.
- Accepted 2026-10-22: the card Remove X moves from the action row to the top right corner. At rest it is a bare glyph, so the primary button stands alone. The red frame returns on hover, on press, and while armed.
