# Isolated UI browser review · 2026-10-02

This is a manual **fixture** check, not Home Assistant/Ingress, provider, WCAG, or production acceptance evidence. The Lit/Vite page was served on `127.0.0.1:5173` and inspected in the Codex in-app browser.

| Check | Observed result | Limit |
| --- | --- | --- |
| First render | Overview shell, tabs, state selector, status copy, and cards rendered | An initial blank page exposed Lit class-field shadowing; reactive fields now use non-emitting `declare` declarations and constructor initialization |
| Route | Selecting Copy changed the hash to `#/copy`, rendered the plan preview, and moved focus to the `Copy playlist` heading | Other routes have pure route tests and build checks, but no full browser matrix |
| Action boundary | `Confirm copy` was disabled with a nearby explanation; the preview states zero writes and no durable plan | No external API is connected |
| Theme | Light and dark views retained the same hierarchy and readable text/status labels | Contrast was not measured across all combinations |
| Responsive | At 390 × 844, cards and facts stacked; tabs remained horizontally scrollable | Companion App safe areas and all viewport sizes are unverified |
| State selector | Partial result changed the visible message and retained-snapshot explanation | Synthetic source state only; it cannot change copy/playback facts |

Build and deterministic checks are described in [the fixture README](README.md). The UI SDD still requires a supported HA/browser matrix, host-context proof, versioned reference captures, accessibility review, and its 92 distinct cases before implementation readiness.
