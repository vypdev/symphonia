# Proposed Home Assistant visual-reference procedure

**Drafted:** 2026-09-27. **Approval:** pending product/UX and accessibility review. This is a procedure proposal for `RG-006`, not an accepted baseline or evidence that Symphonia visually matches Home Assistant.

## Candidate references

The public [Home Assistant demo](https://demo.home-assistant.io/) is the primary capture target. The pinned [Gateway reference set](https://github.com/vypdev/homeassistant-gateway/tree/1ed75be9f8fabdab386db0fe4320cfb0f67d4f42/docs/ui-reference/home-assistant) documents public-demo captures dated 2026-08-05, including Settings and Automations at 1280×720 and 390×844. It does not identify a Home Assistant release for each image and includes no approved dark-theme reference; therefore it can guide **candidate** hierarchy/density review but cannot itself become Symphonia's versioned official baseline.

Candidate screen pairs for the first review:

| Home Assistant surface | Symphonia fixture/product surface | Compare |
| --- | --- | --- |
| Settings landing, wide and phone | Connections | heading, settings rows, spacing, action hierarchy, mobile reflow |
| Automations list, wide and phone | Library and Activity | flat navigation, filters/list density, row/status treatment, partial/empty states |
| Developer Tools States, wide and phone | Copy review and later diagnostics | dense evidence, bounded scrolling, labels, actions and responsive alternatives |

These are **comparative analogues**, not claims that music operations are Home Assistant automations or that one screenshot defines interaction behavior.

## Capture manifest fields

For every accepted image, record: `reference_id`, official URL and route, Home Assistant Core/frontend version or exact source commit, capture UTC timestamp, viewport and device pixel ratio, browser/OS version, theme, locale and direction, public-data provenance, screenshot path and SHA-256, capture command/configuration, and reviewer. Keep immutable historical entries; a new release appends a new entry and changes a separate current pointer. Never overwrite an old accepted image or store account, token, session cookie, private dashboard, provider library, or browser-profile export.

Capture the official reference and the matching Symphonia catalog/feature fixture in the same declared browser engine and geometry, with fonts loaded and transient loading finished. If the public demo cannot supply a dark theme, mark dark comparison unavailable; do not relabel a browser color-scheme override as an official dark capture. Use official documentation/source and interaction tests for behavior that screenshots cannot establish.

## Review and change control

1. The contributor records the manifest and captures, then compares hierarchy, density, geometry, type, borders, navigation, focus, status and actions at wide and phone sizes. They document each observed mismatch, not only pixel diffs.
2. A separate product/UX reviewer accepts parity or records an intentional divergence with reference, reason, user-visible consequence and fallback. An accessibility reviewer checks focus, keyboard, text scaling and contrast where a visual divergence affects interaction.
3. A baseline update requires a written reason: Home Assistant evolution, Symphonia defect correction, or intentional accessibility/product divergence. Regenerating snapshots never self-approves a change.
4. Before each release, revalidate the declared Home Assistant/browser matrix and current reference pointer. A new HA component or iframe contract triggers review of the affected families and the support matrix, not an automatic screenshot replacement.

The current static [UI fixture](README.md) has no approved browser capture. Browser automation of its local `file:` URL was blocked in the current environment on 2026-09-27; this procedure must be executed in an authorized test environment before the SDD can advance.
