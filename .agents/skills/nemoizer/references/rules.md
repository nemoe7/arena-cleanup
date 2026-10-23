<!-- nonemo: NMO100; nonemo: NMO901; nonemo: STE100; nonemo: HMN400; nonemo: HMN600 -->
# Nemoizer rules

| ID | Avoid | Use |
| --- | --- | --- |
| `NMO100` | `transmit`, `kind` | send, type |
| `NMO901` | `pick`, `repository` | select, repo (manual review) |

## Rotations

Each row matches the stem, so `picked`, `picking`, and `picks` all rotate to `select`. Add a row to the skill's rotation table and a pattern in `scripts/nemoize.py`: one table, one source.

A word that shares the stem but stands on its own, like `pickle`, carries a marker instead of a narrower pattern.

A row replaces its word as plain text, in lower, capital, and upper case. Stem exceptions use their own plain words: `picker` and `pickers` become `selector` and `selectors`, and `repositories` becomes `repos`.

## Exclusions

- Use `nonemo: <id>` to suppress only the named rule on that line.
- For file scope, place `nonemo: <id>` in the first three lines with no avoided word before the marker.
- Use any comment syntax for `nonemo: <id>`; the scanner reads text, not syntax.
- Apply an exclusion only to a known matching rule ID.
- Do not rewrite exclusion markers or the rotation table, and apply only unsuppressed rotations and straight-quote replacements for curly quotation marks.
- Print every nonemo marker with its path, line, rule ID, scope, and text when `nemoizer collect` or `--ignores` is used, and print every `nonemo` marker and manual-review finding through `scripts/markers.py` when `nemoizer audit` or `--audit` is used.

```python
value = "kind"  # nonemo: NMO100
```

```markdown
<!-- nonemo: NMO901 -->
```

## Prose measurements

| ID | Metric | Cap |
| --- | --- | --- |
| `STE001` | Dangling conjunction at the end of a bullet list item | 0 |
| `STE100` | Semicolons per covered prose line | 0 |
| `STE200` | Words per covered sentence | Instruction or unclassified: 20; explicit description: 25 |
| `STE300` | Nominalizations with a plain-verb replacement | 0 |
| `STE901` | Passive-voice constructions per covered sentence | 0 (manual review) |
| `STE902` | Phrasal verbs per covered sentence | 0 (manual review) |
| `STE903` | Ellipsis (omitted subject, verb, or article) per covered sentence | 0 (manual review) |
| `STE904` | Compound instruction sentence with two distinct commands | 0 (manual review) |
| `STE905` | Noun cluster of four or more consecutive nouns | 0 (manual review) |
| `STE906` | Synonym cluster or duplicate term on one prose line | 0 (manual review) |
| `STE908` | Compound tense (`will have`, `would have`, `has been`) | 0 (manual review) |
| `HMN100` | Staged opener or closer phrase | 0 |
| `HMN200` | Stacked qualifier or intensifier | 0 |
| `HMN300` | AI-favored, inflated, or promotional vocabulary | 0 |
| `HMN400` | `→` arrow in Markdown prose | 0 |
| `HMN500` | Chatbot courtesy or cutoff disclaimer | 0 |
| `HMN600` | Curly quotation marks (`“`, `”`, `‘`, `’`) | 0 |
| `HMN901` | Negative contrast frame (`not X, but Y`) | 0 (manual review) |
| `HMN902` | Aphorism or meta-importance label | 0 (manual review) |
| `HMN903` | Rhetorical setup or strawman opener | 0 (manual review) |
| `HMN904` | Repeated opener across three consecutive sentences | 0 (manual review) |
| `HMN905` | Unspaced em-dash or spaced en-dash clause break | 0 (manual review) |
| `HMN906` | Vague attribution without a named source | 0 (manual review) |
| `HMN907` | Copula avoidance (`serves as`, `stands as`, `boasts`) | 0 (manual review) |
| `HMN908` | Title-Case Bold Label (`- **Label:**`) list item | 0 (manual review) |
| `HMN909` | Two or more consecutive emojis in Markdown prose | 0 (manual review) |
| `HMN910` | Document self-narration (`This section covers`) | 0 (manual review) |
| `NMP100` | Sentences per covered paragraph | General: 4; stricter project override |
| `NMO003` | Missing serial comma in a three-item list | 0 |

Default scans run `NMO100` and `NMO901` rotations, `NMO003` serial-comma checks, `STE001`, `STE100`, `STE200`, `STE300`, and `STE901`–`STE908` style checks, `HMN100`–`HMN600` and `HMN901`–`HMN910` human-prose checks, and `NMP100` paragraph checks. `--context description` selects 25 words; other contexts use 20.

`nemoizer prose --context instruction --paragraph-cap 4 <paths>` retains the JSON-only measurement interface. Paths are required.

Findings carry rule, path, line, column, count, cap, and review status. Over-cap counts are review candidates, not meaning judgments; length checks do not rewrite text.

Native counters exclude inline code and fenced code, and count ordinary pipe-table cells separately. Paragraph counts cover prose blocks outside tables, headings, lists, and quotes; this is not a complete Markdown parser.

Code prose comes from the shared comment and docstring extractor. Ordinary code strings are not sentence or paragraph input.

Existing exclusions apply at the reported source line, or at file scope. Unknown IDs remain visible in the collector without suppressing a known rule; an unreadable or non-text file is marked not checked.

## Test assertion review

| ID | Candidate |
| --- | --- |
| `NMT100` | Direct prose-literal comparison or membership check against a named output channel |
| `NMT200` | Literal equality-style assertion against a known measurement name |

Default scans apply `NMT100` and `NMT200` to discovered tests and recognized helpers. Discovery reads pytest.ini, test names, and test declarations.

`--test-helper <path>` includes another helper and can repeat. Imports alone do not classify production files as tests.

Static discovery can miss dynamic helpers. `nemoizer review-tests <paths>` retains explicit scope and JSON coverage without executing or rewriting tests.

The Python parser covers bare assertions and selected `self` or `cls` assertion methods. JavaScript uses an existing Acorn parser for selected Node `assert` calls. An unavailable parser is marked not checked without an installation. Default checks fail with status 2 when a required parser is unavailable.

Parser resolution starts at the linter directory, not at a target path or the current working directory.

Known output names include stdout, stderr, output, out, and err. Measurement names include geometry, timeout, duration, token count, and byte count fields. Configured expectations and growth comparisons are not flagged.

Assertion diagnostic messages and quoted fixture inputs are not expected-output checks. A reported literal can still be required executable, protocol, or verbatim data. These patterns do not prove a semantic violation.

Existing rule-specific exclusions and the collector apply. Exit status is 1 for candidates, 2 for parser errors or invalid arguments, and 0 otherwise. Not-checked coverage is not proof of a complete review.

## Legacy rule IDs

Legacy `P`, `T`, and `N` rule IDs are not supported.
