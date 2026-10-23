# `nuu` CLI Reference

`scripts/nuu` (`scripts/uiux.py`) is the single command-line entry point for UI/UX audits, system proposals, design records, measurements, and screenshot annotations.

## Subcommands and Short Flags

| Subcommand | Purpose | Arguments and Shorthands |
| --- | --- | --- |
| `search` | Search vendored design catalogs | `<query>`, `-d, --dataset <name>`, `-s, --stack <name>`, `-n, --limit <n>`, `-j, --json` |
| `system` | Generate a five-part design system proposal | `<query>`, `-p, --project <name>`, `-s, --stack <name>`, `-w, --write [path]`, `-f, --force`, `-j, --json` |
| `record` | Initialize or check `docs/design.md` | `<init\|check>`, `-r, --root <path>`, `-p, --path <rel>`, `-t, --title <text>`, `-s, --status <state>`, `-f, --force`, `-j, --json` |
| `asset` | Fetch, verify, or record licensed assets | `<fetch\|verify\|record>`, `-r, --root <path>`, `-u, --url <https-url>`, `-o, --output <rel>`, `-s, --sha256 <hex>`, `-l, --license <spdx>`, `-a, --attribution <text>`, `-p, --purpose <text>`, `-d, --design-doc <rel>`, `-f, --force`, `-j, --json` |
| `extract` | Extract candidate tokens from source or measure JSON | `-r, --root <path>`, `-m, --measure <path>`, `-o, --output <rel>`, `-f, --force`, `-j, --json` |
| `check` | Check computed-style measure JSON against the sheet | `<report>`, `-s, --sheet <path>`, `-g, --scale <px>`, `-d, --density`, `-j, --json` |
| `density` | Check row/card ink ratio (`UIX205`), sibling gaps (`UIX206`), and control width caps (`UIX207`) | `<report>` |
| `ruler` | Measure pixel distance between two `x,y` guides | `-f, --from <x,y>`, `-t, --to <x,y>`, `-g, --scale <px>`, `-j, --json` |
| `annotate` | Render boxes, arrows, labels, and callouts on a PNG | `-i, --input <png>`, `-o, --output <png>`, `-b, --box <spec>`, `-l, --label <spec>`, `-a, --arrow <spec>`, `-c, --callout <spec>`, `-s, --spec <json>`, `-j, --json` |
| `audit` | Run source, measure, flow, and rendered a11y checks | `-r, --root <path>`, `-u, --url <url>`, `-s, --sheet <path>`, `-m, --measure <path>`, `-f, --flows <json>`, `-c, --change <spec>`, `-A, --allow-live-edits`, `-R, --ready <selector>`, `-o, --out <dir>`, `-j, --json` |

## Audit Coverage (`UIX101`–`UIX306`)

| Code | Pass | Condition |
| --- | --- | --- |
| `UIX101`–`UIX103` | Source / browser | Missing control accessible name, image `alt`, form label, heading skip, `outline: none` without `:focus-visible`, or horizontal overflow |
| `UIX104` | Browser (`--ready`) | Declared `--ready SELECTOR` did not match a visible element within the timeout |
| `UIX201`–`UIX204` | Measure (`--measure`) | Off-scale spacing, off-ramp typography, unapproved border radius, or text contrast below 4.5:1 (`3:1` large text) |
| `UIX205`–`UIX207` | Density (`density`, `--density`) | Row/card ink ratio below `0.25` at `>= 900` px (`UIX205`), sibling horizontal gap `> 320` px and `> 40%` width (`UIX206`), or form control width `> 480` px (`UIX207`) |
| `UIX301` | Rendered `a11y` | Landmarks (`<main>` or `[role="main"]`) and skip-link target missing or broken |
| `UIX302` | Rendered `a11y` | Visible interactive control without an accessible name or with `aria-hidden="true"` while focusable |
| `UIX303` | Rendered `a11y` | Visible interactive control with bounding box smaller than `24x24` CSS px |
| `UIX304` | Rendered `a11y` | Interactive control whose `:focus-visible` ring is clipped or identical to its unfocused outline/box-shadow |
| `UIX305` | Rendered `a11y` | Invalid `role`, missing required ARIA state (`aria-checked`, `aria-expanded`, `aria-selected`), or broken `aria-labelledby` / `aria-describedby` / `aria-controls` ID target |
| `UIX306` | Rendered `a11y` | Stylesheet animation or transition without a `@media (prefers-reduced-motion: reduce)` rule |

## Optional Recipes

- Scroll-edge fade (`@supports (animation-timeline: scroll(self))`): fade scrollable containers (`12px` edge height over a `192px` scroll ramp) while keeping non-scrollable containers unmasked.

```css
:root { --edge-fade: 12px; --edge-ramp: 192px; }
@property --edge-start { syntax: "<length>"; inherits: false; initial-value: 0px; }
@property --edge-end { syntax: "<length>"; inherits: false; initial-value: 0px; }
@media (prefers-reduced-motion: no-preference) {
  @supports (animation-timeline: scroll(self)) {
    .scroll-panel {
      mask-image: linear-gradient(to bottom, transparent, black var(--edge-start), black calc(100% - var(--edge-end)), transparent);
      animation: edge-start linear both, edge-end linear both;
      animation-timeline: scroll(self), scroll(self);
      animation-range: 0px var(--edge-ramp), calc(100% - var(--edge-ramp)) 100%;
    }
    @keyframes edge-start { from { --edge-start: 0px; } to { --edge-start: var(--edge-fade); } }
    @keyframes edge-end { from { --edge-end: var(--edge-fade); } to { --edge-end: 0px; } }
  }
}
```

