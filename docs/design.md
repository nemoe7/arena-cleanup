# Design record

The one design record for the arena-cleanup web app. The sections follow the nemo-ui-ux skill template. The token source is the `:root` block in `ui/static/index.html`.

## Purpose and status

- Goal: clean an arena branch (rewrite, sign, push) from a browser, on a phone or a desktop.
- Scope: the dashboard, the repo view, and the settings view.
- Constraints: one HTML file, no build step, and a dark theme only. Fonts and icons ship with the page, so nothing loads from the network.
- Acceptance checks: the pytest suite in `tests/`, screenshots at 1280 and 360 px, and the nemo-ui-ux measure reports.
- Design status: accepted for the four views. The audit findings of 2026-10-22 are fixed.

## Users, tasks, and language

- User group: one developer who owns the repos and the GitHub account. No research beyond that use.
- Primary tasks: add a repo, run a cleanup, read the log, and keep the settings right. Settings: GitHub access, signing, identity, and the claim rules.
- Repo: a clone the server registered. Identifier: the server-minted `id`. The card shows `name` only.
- Arena branch: a branch under the `arena/` prefix with its PR and check count.
- Run: one engine execution with five phases: Prepare, PR checks, Rewrite and sign, Push, Finish.

## Journeys and information architecture

- Entry: the dashboard at `/`. The header holds the brand, the tool dots, and one icon button (Settings).
- Dashboard to repo: a click on the card or Enter on a focused card. The name underlines on hover. Back: the All repos button.
- Settings opens from the header, and Back returns to the previous view.
- Delete an arena branch: the trash control on a sidebar row opens the modal, and Delete removes the branch on origin. The sidebar, the select, and the dashboard refresh after it.
- Recovery: a failed run keeps its log open, and a failed load shows a banner with the error text. The service worker caches the shell only, never server state.

## Screens and states

- Dashboard: sort select and Reload button in the head, add bar. One repo row per repo above 1200 px, repo cards at 1200 px and below. Empty: a hint with the add command. Error: a banner above the rows. A row or card shows the branch. The repo name is a button that opens the repo, and a click on the card body does the same. The card itself has no role. Each arena row has two lines at every width: the branch name, then `↑ N` and the PR pill. `↑ N` is the net count, the commits that branch holds beyond `origin/<default>` minus the commits `origin/<default>` holds beyond it, with a tooltip. The chip hides below 1, so absorbed work and a default branch that moved on show no chip. No dot sits before the name or in the PR pill, the pill colour carries the state. The Remove trash glyph sits top right, bare at rest. A red frame comes on hover, on press, and while armed.
- Repo: a 320 px sidebar, then the run card left and the options card right, and the log card below both. The run card holds the status and the phase list. The log card holds the open log of the latest run and takes the height that is left, down to a 160 px floor. Both come back after a return to the view or a restart. The main column pins to the window like the sidebar, so only the log scrolls. The options card head carries the one run button. It reads Clean & Push while idle and Cancel while a run is live. Each option is one row: label, control, and a trailing action or readout. No hint texts. Dry Run, Ignore PR Checks, Update Tags (checked by default), and No lease are checkboxes. No lease is the one danger-coloured option: checked, the run pushes with `git push --force` and no lease, and its tooltip names the two other effects of `-f`. PR check timeout is a slider with the number beside it. It snaps to 0, 5, 10, 15, 20, 30, 45, 60, 90, or 120 minutes. Target branch lists the default branch first and never an `arena/*` branch. Arena branch appears with two or more arena branches, newest tip first. Each option reads `branch · day`, and the full stamp sits in its title. The chosen one goes to the run as `--arena`. The sidebar holds the repo facts and the arena rows on top. The commit list fills the rest and scrolls on its own. Its hint is the commit count with thousands separators. The list holds 30 commits a page, and a scroll near the end appends the older page. Each row shows hash, subject, author, and date. Reload sits in its label. Each arena row shows the PR state and is a button that selects the branch to pull from. The page runs the full flow only. `strip` is a CLI command. Browse under Remove paths opens the HEAD tree of the clone, one level per request. A click on a row or its plus adds the chip. Log rows show the clock of the browser. Remove on a card arms on the first click and deletes the URL clone on the second. States: idle, running, done, failed, cancelled. A managed clone goes back to origin before every run. The server fetches, checks out the default branch, resets hard, and drops local `arena/*` copies.
- Settings: two columns above 1200 px. Left: Identity (name, email, Save), Claimed commits (two chip lists, Save), About. Right: GitHub sign-in, How git reaches GitHub, signing cards. One column at 1200 px and below, in the order Identity, GitHub, signing, Claimed commits, About. How git reaches GitHub and About fold, and open on a click. The first opens on its own when git has no credential helper. Signing cards: gpg banner when gpg is missing, key list, create card, GitHub key steps. Disabled: Create key while gpg is missing. Error: the banner names the failed check. Each card loads on its own.
- Offline: the service worker serves the shell. Data requests fail with the normal error banner.
- Loading and permission states: not run as separate checks.

## Design system and tokens

### Colour

- Roles: `bg`, `surface`, `surface-2`, `surface-3`, `line`, `line-2`, `text`, `muted`, `dim`, `accent`, `accent-hi`, `accent-deep`, `accent-deep-hi`, `accent-soft`, `ok`, `warn`, `err`, `info`.
- One dark theme, `color-scheme: dark`. Contrast checks: white on the primary button 5.3:1 at rest and 5.9:1 on hover, and `dim` text 5.1:1 on a card. `accent` itself gives 3.9:1 under white, so it fills checked boxes and marks rows, never a text button.

### Type

- Inter (variable) for text, Monaspace Neon (variable) for paths, hashes, commands, and the log. Both ship as Latin subset woff2 files under `ui/static/fonts/`.
- The head preloads both files at its top and paints them with `font-display: block`. A reload never flashes a fallback face. Each pairs with a metric-matched local fallback face, Arial for Inter and Courier New for Monaspace Neon. Line boxes hold if a file fails to load.
- Desktop ramp: `--fs-1` 12 px for metadata and mono details, `--fs-2` 13 px for controls and labels. `--fs-3` 14 px for body, names, and buttons, `--fs-4` 16 px for a view title, `--fs-5` 20 px for the page title.
- Phone ramp at 640 px and below: body 12 to 15 px, fields 16 px, and title 20 px. The 16 px fields keep iOS from zooming.
- Weights: 400, 520 to 640 for labels and names, 600 for headings and bold runs.

### Icons

- Lucide 1.61.0, vendored one glyph at a time into the `ICONS` map in `index.html`. Each glyph keeps its 24 px grid and its 2 px stroke in the text color.
- Three size tokens set the glyph box per place at every width. `--ico-s` is 14 px for inline glyphs: the commit check, the stand-in for a missing author picture, the chip X, and the pill arrow. `--ico-m` is 16 px for buttons, phase rows, tree rows, and banners. `--ico-l` is 18 px for icon buttons, the card mark, and the brand mark. A glyph in running text stays at 1 em.
- Navigation and file glyphs in use: arrow-left, settings, arrow-up, arrow-down, chevron-right, folder, folder-tree, file, and plus.
- State and action glyphs in use: check, x, triangle-alert, minus, circle-small, loader-circle, git-branch, refresh-cw, copy, user, and broom-sparkles.
- Buttons with a glyph: Reload is `refresh-cw` alone, named `Reload commits` in `aria-label` and `title`. Copy log is `copy` alone, named `Copy log` the same way. Re-check and Retry lead with `refresh-cw`, Copy public key with `copy`, and Browse with `folder-tree`. Every other button keeps its word alone.
- Clean buttons: every `Clean & Push` button carries `broom-sparkles`, the broom alone when idle, and the sparkles appear on hover and focus. Every button leads with the glyph at `--ico-m` before its words, the dashboard rows and cards included. The `Cancel` state is the word alone.
- Static slots carry `data-icon="<name>"`, and the boot fills them. The brand mark is `broom-sparkles` in the accent, the same glyph as the app icon.
- App icon: `scripts/app_icon.py` draws `ui/static/icons/*.png` from the `broom-sparkles` paths. The favicon and the regular PWA pictures carry the accent glyph alone on a transparent ground. The maskable picture and the Apple touch icon add the `--surface` background, full bleed, with the glyph inside the safe zone.
- No text glyphs stand in for icons. The licence sits beside the page in `ui/static/LICENSE-lucide.txt`.

### Layout

- Spacing scale: 2, 4, 6, 8, 10, 12, 16, 20, 24, and 32 px, with 1 px for borders.
- Page padding `--pad`: 20 px, 16 px at 1200 px and below.
- Breakpoints, the nuu trio in em, one change each: 75em, 56.25em, and 40em. That is 1200, 900, and 640 px at the 16 px browser default, and the em unit moves each switch with the reader's font size. 1200 px stacks the options card over the run card and folds the repo rows into cards. It puts the settings in one column and tightens the padding. 900 px stacks the sidebar below the cards and the repo cards into one column, and the page scrolls as one. 640 px switches to the phone ramp, 44 px targets, and stacked rows. The options sit in one column at every width. No other width carries a rule.
- Radius: 12 px for cards, 8 px for buttons and fields, and 1000 px for pills. The tree select takes 6 px, the checkbox 4 px.

### Theme and motion

- Transitions of 120 to 180 ms on transform, opacity, border, and background. `prefers-reduced-motion` stops them.
- Scroll-edge fade, the nuu recipe: the commit list and the log carry `scroll-panel`. A scrolled edge fades over 12 px, and the fade grows and shrinks over a 192 px scroll ramp. A panel that does not scroll stays unmasked. The rule needs `animation-timeline: scroll(self)` and no reduced-motion preference. Other scrolling regions keep their edges.

## Components and contracts

- `btn`: 34 px high, 12 px side padding, 8 px radius, and 44 px high on a phone. Variants: `primary`, `ghost`, and `icon-btn`. All of them are flat: a fill and a 1 px border, no highlight, and no shadow.
- `pill`: dot and word, 8 px gap, 1000 px radius, `ok`, `warn`, `mono` variants.
- `commit`: grid `auto minmax(0, 1fr)`, the subject clamped to two lines with an ellipsis, the metadata on a second row. The row is a button with `aria-expanded`, and a tap shows the whole subject. The metadata carries the author's GitHub picture, 20 px and round, or a `user` glyph in the same disc when the server has none.
- `row-btn.select`: a sidebar arena row that is a button with `aria-pressed`. The selected row carries a 2 px accent bar and the text colour. The name reads `Pull from <branch>`. Rows and the timeout slider are 44 px high on a phone.
- `arena-item`: the arena row and its `arena-del` icon button side by side. The trash glyph is dim until hover, then reads in the error tint. The name reads `Delete <branch>`.
- `modal`: a `dialog` of 420 px at most, with a title, one paragraph, and Cancel then Delete at the right. The backdrop dims the page. Escape and Cancel close it without a request.
- `opt.row`: a grid of three columns, `128px minmax(0, 1fr) auto`, for the label, the control, and the trailing Browse or slider readout. `check`: a label with a drawn checkbox. The box is 16 px, 20 px on a phone, with a 4 px radius and the surface-2 fill. Checked, it takes the accent fill and a white Lucide check. `danger` fills a checked destructive option with the warn colour and a dark check. On a phone the checkboxes form a grid with 160 px columns. Browse, the fold head, and the 16 px path field are 44 px targets there.
- `phase`: a row with the state glyph, the name, a count, and the time. The count comes from the engine's lines. PR checks reads `passed/total`. Rewrite and sign reads `collecting N commits`, then `signing X/Y`, then `signed X commits`. Push reads `moving`, `pushing`, then `pushed X tags`, and stays empty without a tag. A dry run reads `would sign` and `would move`. Before a count the row carries the name alone.
- `repo-card`: above 1200 px a subgrid row on the columns of `grid`, so the columns align across rows. Left to right: the icon, the name, the branch pill, the arena rows stacked behind a hairline, Clean, and Remove with the trash glyph. The arena area takes the free width, so the buttons sit at the right edge. In a row an arena row is one line: the name, the ahead chip, and the PR pill. At 1200 px and below a grid card. The icon, the name, and Remove sit on top on one centre line, then the arena rows, and Clean & Push bottom right. The branch chip stays in the rows, and an unavailable card shows its reason in the arena area.
- `sign-row`: label column of 120 px and a value column. On a phone the label takes a full row.
- `sign-fields`: name and e-mail side by side, one column on a phone.
- `card.fold`: a `details` card. The `summary` is the card head with a `show` or `hide` mark at the right, and the body opens below it. Closed, the head has no bottom border.
- `banner`: `err`, `warn`, `ok` variants with an icon and one sentence of action.
- `run button`: one button with `data-state` idle, starting, or running. Idle reads Clean & Push and is the primary. Starting is disabled until the job id arrives. Running reads Cancel as a plain button.
- `tree`: the path selector. Rows are `treeitem`s with `aria-level`. A folder row carries `aria-expanded` and loads its children on the first open. The trailing `tree-select` button toggles the path and reports `aria-pressed`. Rows and select buttons grow to 44 px on a phone.

## Accessibility and inclusion

- Target: WCAG 2.2 AA for keyboard use and names. Applied so far: a skip link, `aria-label` on icon buttons, `role="status"` for the run state, and focus rings. Targets are 44 px on a phone and at least 24 px under a pointer.
- Test methods: the browser walk in `scripts/walk.py` (keyboard and names) and the measure reports (target sizes).
- Not run: screen reader sessions, contrast measurement.

## Content and assets

- Copy follows ASD-STE100: short sentences, one action per banner, no jargon beyond git and GitHub terms.
- Locale: English only. Dates use the browser locale.
- Fonts: Inter and Monaspace Neon, SIL Open Font License 1.1, see `ui/static/fonts/LICENSE.txt`. Icons: Lucide, ISC, see `ui/static/LICENSE-lucide.txt`.

## Behavior and data

- The repo registry and settings live on the server under `ARENA_DATA`. The page keeps no state beyond the open view.
- Pictures: the server keeps the GitHub picture of each author under `ARENA_DATA/avatars/`, one lookup per address. A noreply address names the user, any other costs one `gh api` call. A picture lives 30 days after its last use, a use renews it, and expired ones get pruned. The page loads them from the server, never from GitHub.
- Commits: the commits API answers 30 a page with a `next` cursor, the sha of the last commit of a full page. `before=<sha>` answers the page after it. Reload starts at the first page again.
- Latest run: the server keeps the newest run of each repo in memory and writes the finished one to `ARENA_DATA/jobs/`. The repo view asks for it on open. A live run streams on from its first line. A finished run paints at once with its log, phases, and status. A removed repo takes its saved run with it.
- Defaults: PR check timeout 15 minutes, dry run off.
- Validation: the add bar accepts a clone URL, a GitHub page address, or a path. Another shape gets an error line under the field, with `aria-invalid` and `aria-describedby` on the field until the next keystroke. The server answers errors as text the banner shows.
- Retries: none automatic. Re-check and Reload buttons repeat a read.
- Fetch: the server runs `git fetch --prune origin` in every repo at the top of each clock minute. The timer aligns to the wall clock, so it never drifts. A page load fetches once, and the dashboard Reload button fetches now. A repo with a run in flight waits for the next tick.
- One fetch at a time: a fetch that arrives while one runs waits for it and skips its own. The server skips a fetch within ten seconds of the last one, except from the Reload button. A fetch swaps fresh statuses into the cache, it never empties it. The dashboard shows `Loading repos…` until the first answer.

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
- Accepted 2026-10-22: the even spacing scale with 1 px borders stays. The 8 px house scale stays out, because the dense rows need 6 and 10 px steps.
- Accepted 2026-10-22: two breakpoints at 980 and 720 px. 1180 px is the content width, not a breakpoint. Four option columns went, because the divergence control overflowed between 981 and 1179 px.
- Accepted 2026-10-22: in a narrow cell a segmented control wraps whole buttons onto a second row, never words.
- Accepted 2026-10-22: a shallow history. The dashboard is the root entry and a sub-view is at most one entry deep. One Back leaves a sub-view, the next one leaves the page.
- Accepted 2026-10-22: no command switch on the repo page. A local rewrite without a push is a terminal task, so `strip` lives in the CLI alone.
- Accepted 2026-10-22: the whole options card folds, not the Target branch row alone. The select names the default branch first, keeps the empty value, and lists no `arena/*` branch. The server refuses one too.
- Accepted 2026-10-22: with two or more arena branches the page selects one, newest tip first, in the options card. The engine gained `--arena NAME` for it and keeps the full flow. The page never passes `-b arena/*`.
- Accepted 2026-10-22: the sidebar grows to 320 px. The commit list sits below the repo facts and the arena rows. The HEAD block goes. The hash leads each commit row. Below 900 px the sidebar stacks under the run card instead of hiding. The commit list then grows with the page: one scroll per screen.
- Accepted 2026-10-22: a click on a sidebar arena row selects the arena branch the run pulls from. The Arena branch select follows the row and the row follows the select. The marked row never sets the target branch. With one arena branch the row only shows which branch that is.
- Accepted 2026-10-22: the options card loses its hint texts and the task note above it. Each option is one row. The switches become checkboxes with Title Case labels. Update Tags is the positive form of `--no-tags`. Keep arena branch goes. The reset before every run drops local copies, so a kept branch never reaches the next run. The timeout is a slider with ten stops and a readout.
- Accepted 2026-10-22: a managed clone holds nothing of its own. The server resets it to origin before every run and drops local `arena/*` copies. The page loses the Reset button, the dirty chip, and On divergence. `--on-divergence` stays a CLI flag.
- Accepted 2026-10-22: the card and the sidebar show how far each arena branch is ahead of the default branch. The clone's own drift stays out of sight. Nobody commits in the container, and the engine handles that divergence itself.
- Accepted 2026-10-22: the primary button reads Clean & Push. The phase list keeps Publish for the push, tags, and cleanup step.
- Accepted 2026-10-22: a tree selector for Remove paths. It reads `git ls-tree` of HEAD in the clone, so it works for path repos and never calls GitHub. File contents stay out. A path only old commits carried stays a typed chip.
- Accepted 2026-10-23: the breakpoints move to the nuu widths 1200, 900, and 640 px. 1200 folds the options, 900 stacks the page, 640 is the phone. Between 981 and 1200 px the options lose their two columns, and nothing clips.
- Accepted 2026-10-23: an audit against this record found eight lines that did not hold. The page moved to the record. Pointer targets are at least 24 px. Every banner leads with its glyph, and the type weights stay in the set.
- Accepted 2026-10-23: the primary button takes `accent-deep`, 5.3:1 under white, and `accent-deep-hi` on hover. The `accent` token stays for fills and marks.
- Accepted 2026-10-23: the options card puts the selects and Remove paths left, PR check timeout and the checkboxes right. One grid with column-locked rows: PR check timeout shares the Target branch row, the checks share the next row.
- Accepted 2026-10-23: the page draws the checkboxes. `appearance: none` drops the browser box, so the boxes match the select and the fields in every browser.
- Accepted 2026-10-22: the card Remove X moves from the action row to the top right corner. At rest it is a bare glyph, so the primary button stands alone. The red frame returns on hover, on press, and while armed.
- Accepted 2026-10-23: a commit subject wraps to two lines, then an ellipsis. The row is a button, and a tap shows the whole subject on a phone without hover.
- Accepted 2026-10-23: the log of the latest run stays open under the phase list. Show log goes, and Copy log is a glyph button. An empty log reads `No run yet.`
- Accepted 2026-10-23: three icon size tokens at every width, 14, 16, and 18 px. The glyphs no longer follow the text size. That rule left most of them at 12 or 13 px on a desktop.
- Accepted 2026-10-23: the arena row on a card is two lines at every width, the name first. The dots before the name and in the PR pill are gone, the pill colour is the signal.
- Accepted 2026-10-23: the ahead chip shows the net count and hides below 1. Absorbed commits read 0, and a default branch that moved on reads below 0.
- Accepted 2026-10-23: the repo name is the control that opens the repo. The card lost its button role, so Remove and Clean & Push no longer sit inside a control.
- Accepted 2026-10-23: Monaspace Neon replaces JetBrains Mono for monospace, Inter stays for prose. Both load by the offline fonts recipe: one subset variable file each, preloaded, `font-display: block`, and a metric-matched local fallback face.
- Accepted 2026-10-23: the ahead counts read origin as it is now. The server fetches at the top of each clock minute. A page load fetches once, and a dashboard Reload button fetches on demand.
- Accepted 2026-10-23: the repo view reattaches to the latest run. The server saves each finished run per repo, so the log survives a return to the view and a restart.
- Accepted 2026-10-23: one fetch of every origin at a time, with a ten second debounce that the Reload button skips. Fresh statuses swap into the cache after the fetch, and the dashboard reads `Loading repos…` until the first answer.
- Accepted 2026-10-23: the PR pill counts checks by the engine rule, one entry per check name, a pass over a superseded attempt. The rule lives in the engine, and the server calls it.
- Accepted 2026-10-23: the run card sits left and the options card right, the log card below both at full width. The main column pins to the window and the log fills the rest with a 160 px floor, so the page never scrolls. 1200 px stacks the two cards, options first.
- Accepted 2026-10-23: Clean & Push and Cancel are one button with two states, in the options card head. The options card no longer folds, and its chevron is gone.
- Accepted 2026-10-23: the primary button is flat. Its inset top highlight and drop shadow read as a bevel, so both are gone.
- Accepted 2026-10-23: the log clock takes `dim`, 5.1:1 on the card. Its own grey read at 2.55:1, under the 4.5:1 floor.
- Accepted 2026-10-23: the run card and the options card stretch to one height. The options body has no vertical padding and no rule under its last row, so its rows sit like the phase rows.
- Accepted 2026-10-23: the phase rows lose their hint texts. A row shows a count once the engine reports one: checks and how many still run, commits signed of the total, and tags moved.
- Accepted 2026-10-23: the counts read `passed/total` for the checks, `collecting`, `signing X/Y`, and `signed X commits` for the rewrite, and `moving`, `pushing`, and `pushed X tags` for the push. The Publish row is named Push, and a run without tags leaves it empty.
- Accepted 2026-10-23: the commit rows show the author's GitHub picture for every author. The server caches one picture per address for 30 days after its last use and prunes the rest.
- Accepted 2026-10-23: the app icon and the brand mark are the Lucide `broom-sparkles` glyph in the accent. The regular pictures are the glyph alone, the maskable picture and the Apple touch icon get the dark ground.
- Accepted 2026-10-23: the scroll-edge fade applies to the commit list and the log alone.
- Accepted 2026-10-23: human-facing text says push, not publish, and PR, not pull request. Identifiers, API fields, and the history above keep their words.
- Accepted 2026-10-23: above 1200 px the dashboard shows one full-width row per repo on shared columns. The arena area takes the free width, and Clean and Remove sit at the right edge. An arena row is one line there, and two branches stack. At 1200 px and below the repos stay cards with two-line arena rows. Remove carries the trash glyph at every width. The spread beats the nuu ink ratio: the arena area of a one-branch row reads 0.21 to 0.24, under the 0.25 line.
- Accepted 2026-10-23: the dashboard sorts the repos by the newest arena tip, by name, or by PR state with failures first. The select sits beside Reload and the browser keeps the choice.
- Accepted 2026-10-23: the dashboard Clean & Push button reads the glyph and the words again in rows and cards. A card puts it bottom right and drops the branch chip.
- Accepted 2026-10-23: the commit hint is the count alone, with thousands separators. The list pages 30 at a time, a scroll near the end loads the older page, and Reload restarts.
- Accepted 2026-10-23: each sidebar arena row carries a trash control. A modal names the branch and asks first, with no warning about an open PR. Delete drops the branch on origin and refreshes the views.
- Accepted 2026-10-23: the settings page is two columns above 1200 px. The help cards How git reaches GitHub and About fold at every width. The page drops from 2037 px to 1089 px at 1280, and from 2728 px to 2219 px at 360.
- Accepted 2026-10-24: the three media queries read 75em, 56.25em, and 40em, after the nuu sheet moved its breakpoints to em. Same widths at the 16 px default, earlier switches for a larger browser font.
- Accepted 2026-10-24: four values move to the 4 px scale after the nuu audit. Fields pad 12 px instead of 10, and the pill gap is 8 px instead of 6. The phone keeps the 16 px page padding instead of 14, and its title reads the 20 px ramp size instead of 19. The pill radius reads 1000 px, the same shape on the scale.
- Accepted 2026-10-24: the PR pill and the sidebar dot paint running checks amber, the GitHub pending colour, instead of blue. A PR without checks gets a grey dot. The `info` token keeps the debug log rows.
