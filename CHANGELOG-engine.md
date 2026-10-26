# Engine changelog

This file documents all notable changes to the engine, `arena-cleanup.py`,
from 0.3.0 on. Up to 0.3.0 the engine and the UI shared one number and one
file, `CHANGELOG.md`.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the engine uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.7] - 2026-10-26

- The rewrite and the signing run before the wait for running checks, so
  the push follows the last green check at once. A red check or a cancel
  during the wait puts the branch and its tags back at the fetched tip.
- The checks wait counts check runs GitHub adds during it in its total.
  Heartbeat and final line read `finished/total` from the fresh summary
  instead of the first one.

## [0.3.6] - 2026-10-24

- Log lines print commit hashes at 7 characters, the GitHub short SHA,
  instead of git's own abbreviation.

## [0.3.5] - 2026-10-24

- The file marker suppresses HMN904 for the usage list, and the push
  docstring drops one article. No behaviour change.

## [0.3.4] - 2026-10-24

- nemoizer markers name current rule IDs: NMO901 and STE901 at file
  scope, and the unknown NMO002 goes. No behaviour change.

## [0.3.3] - 2026-10-24

- The divergence docstring lists its two outcomes as bullets under the lead
  line. No behaviour change.

## [0.3.2] - 2026-10-24

- The comment above `__version__` names the split numbers and version
  check. No behaviour change.

## [0.3.1] - 2026-10-24

- Three docstrings and one comment read in the active voice. No behaviour
  change.

## [0.3.0] - 2026-10-23

- The shared history up to this number is in `CHANGELOG.md`.
