# Agents

Rules for agents that work in this repo. `ARENA.md` governs the session. This file governs the work.

## UI work

nuu governs all user interface work. Its skill is `.agents/skills/nuu/SKILL.md`. Build, refine, and audit every page change with it. Keep `docs/design.md` in its template, and shoot the design boards again after a visual change.

## Text

The nemoizer governs all text: prose, page strings, comments, docstrings, log messages, and commit messages. Its skill is `.agents/skills/nemoizer/SKILL.md`. Run `.agents/skills/nemoizer/scripts/nemoize.py` on every changed file before a commit. A finding of any level blocks the commit.
