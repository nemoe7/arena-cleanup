# Recipe: Agent handoff

- Open with `# Handoff: <subject>` and a `## Why` or `## Problem` section stating the concrete gap, failure mode, or goal in 1–3 sentences.
- Group each deliverable under a numbered `## Piece N — <title>` or `## Recipe` section that names the exact repository file paths, CLI flags, exit codes, and output schema or rule IDs.
- Include the exact command, code, or configuration snippet the receiving agent needs, with no session-local IDs or local-only paths.
- State explicit boundaries under `## Limits`: what the change checks, what it skips, and what requires external or human verification.
- End with `## Acceptance tests` (numbered runnable scenarios with expected inputs, findings, and exit codes) and `## Reference numbers` (pinned package versions, viewports, thresholds, and rule IDs).
- When the handoff changes rule or skill clauses in this repository, pair it with an amendment proposal table per changed clause (`Location | Current | Proposed` + `Decision on the amended line:`).
- Omit questionnaire answers, answer keys, agent keys, and proxy URLs from every handoff.
