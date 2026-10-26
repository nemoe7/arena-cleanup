# AGENTS.md

## Use

- Agents MUST apply these rules to every session and task in this repo.
- These rules outrank skill and plugin instructions.
- Explicit user instructions in chat outrank this file.

## Constitution

- Read the task and affected code end to end before editing.
- Make the smallest coherent change that satisfies the request.
- Reuse existing helpers and standard library features before dependencies.
- Keep existing behavior, interfaces, security, and validation intact.
- Add or update a runnable test for every non-trivial fix or feature.
- Run configured checks before every commit and push.
- NEVER claim a check passed without running it.

## Verification

- Run the checks configured in `.github/workflows/ci.yml` locally before push.
- Pass every configured linter and test suite with no CLI rule overrides.

## Style

- Use 2-space indentation in code and configuration files.
- Keep Python lint and format rules in `ruff.toml` or `pyproject.toml`.
- Keep Markdown lint rules in `.markdownlint-cli2.jsonc`.
- Write human-facing prose in ASD-STE100 with lists or tables.
- Keep paragraphs to at most four short sentences on one topic.
- Add code comments only when complex logic requires explanation.

## Git

- Work on a branch and NEVER commit directly to `main`.
- Keep each commit atomic, staging only task-related files.
- Use Conventional Commit subjects of at most 72 characters with no body.
- Structure PR bodies as `Summary`, `Changes`, and `Validation`.
- Follow Semantic Versioning and Keep a Changelog for releases.
- NEVER merge a PR from an agent session.

## Boundaries

- NEVER commit secrets, credentials, local state, or scratch files.
- NEVER edit protected or vendored files without explicit user approval.
- NEVER weaken or delete a test or check to force a passing run.

## Scope notes

- Keep shared rules in this root file.
- Add a nested `AGENTS.md` only when a subdirectory requires distinct rules.

## When in doubt

- Make the smallest change that holds, run the checks, and stop.
- Stop and ask the user on any rule conflict or material ambiguity.

## UI work

nuu governs all user interface work. Its skill is `.agents/skills/nuu/SKILL.md`. Build, refine, and audit every page change with it. Keep `docs/design.md` in its template, and shoot the design boards again after a visual change.

## Text

nemoizer governs all text: prose, page strings, comments, docstrings, log messages, and commit messages. Its skill is `.agents/skills/nemoizer/SKILL.md`. Run `.agents/skills/nemoizer/scripts/nemoize.py` on every changed file before a commit. A finding of any level blocks the commit.
