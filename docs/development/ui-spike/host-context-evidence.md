# RG-006 host-context and compatibility evidence

**Reviewed:** 2026-09-27; local lab updated 2026-10-04. **Status:** partial research; no supported HA/browser matrix or production App-context claim yet. This is evidence for the [UI foundation SDD](../../../specs/home-assistant-native-ui.md), not an implementation contract.

## What the public sources actually establish

| Concern | Official evidence | Consequence for Symphonia |
| --- | --- | --- |
| App Ingress | [App presentation guidance](https://developers.home-assistant.io/docs/apps/presentation/#ingress) says Ingress authenticates and proxies the UI, exposes `X-Ingress-Path`, and supports HTTP, streaming, and WebSockets; [App configuration](https://developers.home-assistant.io/docs/apps/configuration/) defines `ingress`, `ingress_port`, and `ingress_entry`. | Resolve a server-validated base path per request; never assume `/`. These docs do not prove our router/build/asset behavior. |
| Safe area, default | [2026.8 component update](https://developers.home-assistant.io/blog/2026/07/31/frontend-component-updates-2026.8/) says App iframes receive host-managed safe-area padding by default. | Begin with host-managed padding. Do not add the same insets in the App interior by default. |
| Safe area, opt-in | The same update documents `home-assistant/subscribe-properties` with `handleSafeArea: true` and a resulting `safeAreaInsets` property. The [current App panel source](https://github.com/home-assistant/frontend/blob/dev/src/panels/app/ha-panel-app.ts) shows `top`, `right`, `bottom`, and `left` values as CSS-length strings. | Opt-in only if a verified design needs full-bleed content and after validating source, origin, shape, units, and double-padding behavior. The static fixture's `env(safe-area-inset-bottom)` is exploratory, not evidence that the iframe receives HA insets. |
| Other App properties | The current App panel source sends `type: home-assistant/properties`, `narrow`, `route`, and `safeAreaInsets` after subscription. It posts to the iframe using `"*"`; this is source-code evidence, not a promise across releases. | Treat the message as untrusted UI hints, not identity/authorization. Do not assume a correlation ID or a theme/locale/timezone field. Validate `event.source`, same-origin expectation, type, and bounded fields against a supported-version fixture before use. |
| Theme, locale, direction, timezone | The inspected public App-properties message contains none of these fields. No public App iframe contract for them was verified in this research. | Use deterministic browser/standalone fallbacks (`prefers-color-scheme`, `navigator.language`, `Intl` timezone, locale-derived direction) until another *public, versioned and tested* source is proven. This may differ from Home Assistant's per-user settings and must be disclosed. Never read parent DOM or private storage to close the gap. |
| Tooling | [Lit components](https://lit.dev/docs/components/overview/) are custom elements; [Lit tooling guidance](https://lit.dev/docs/tools/development/) supports TypeScript and Vite; [Vite build documentation](https://vite.dev/guide/build.html) describes production assets. [ADR 0005](../../decisions/0005-lit-typescript-vite-ui.md) records owner approval. | The stack decision is closed. Ingress asset/base-path behavior, bundle cost, browser matrix, accessibility, and catalog build remain unverified. |

The [isolated Lit build spike](../ui-lit-spike/README.md) used Node 24.20.0, Lit 3.3.3, TypeScript 7.0.2, Vite 8.3.1, and a pinned npm lockfile on 2026-09-27. Type-checking, three pure fallback tests, a presentation-import guard, Vite build, and relative-asset inspection passed. Its single JS asset was **19,327 bytes / 7,529 bytes gzip**. This is a tiny synthetic sample, not a budget or performance result for the full component catalog, a modest HA device, or Ingress. The CI job reruns these checks on Node 24; browser and device evidence remain open.

The `dev` branch of Home Assistant frontend is mutable. Before releasing, pin the exact supported tag/commit and verify the resulting browser behavior. The 2026.8 blog establishes the introduction of safe-area behavior; it does not establish that every earlier or later installation exposes identical properties.

## Candidate matrix — not yet a support promise

| Target | Candidate | Evidence still required |
| --- | --- | --- |
| Home Assistant Core/App panel | 2026.8 and a current supported release | Real Supervisor/App Ingress tests for default and opted-in safe area, property changes, origin/source, reload/deep link, and user theme/locale behavior. |
| Desktop browser | Current stable Chromium, Firefox, Safari | Keyboard/a11y, theme, zoom, RTL, responsive and route/asset checks inside Ingress; record exact versions and OS. |
| Companion App | Current Android WebView and iOS WKWebView | Narrow/safe-area/virtual-keyboard, orientation, session and deep-link tests; record app/OS/webview versions. |
| Standalone fallback | Current stable browser matrix | Same feature fixture semantics without Home Assistant framing; authenticated route behavior when that profile is designed. |

An unsupported or absent host property is not an error by itself: the UI remains readable with fallback tokens and host-managed safe area. A confirmed compatibility hazard gets a versioned warning; no speculative warning based only on a version string.

## Required test sequence before marking the SDD ready

1. Record a disposable HA installation's Core, Supervisor, frontend commit/build, Companion App (if applicable), browser, OS, theme, locale, direction, and viewport. Use public/demo data only for visual capture.
2. Open the App through a non-root Ingress prefix; inspect `X-Ingress-Path` at the trusted server boundary. Reload and deep-link each fixture route; verify relative assets, HTTP, and any WebSocket/SSE path stay under that prefix.
3. In 2026.8+, compare default host-managed padding against `handleSafeArea: true` subscription on phone/orientation changes. Validate that top/bottom/side insets are applied exactly once and that the host header is not duplicated inside the App.
4. Capture the exact `home-assistant/properties` message fields from an authorized disposable instance without saving private data. Reject wrong source/origin, malformed objects, oversized values, unsafe CSS lengths, and unexpected fields in adapter tests. Check what happens on unsubscribe/reload.
5. Change Home Assistant user theme, locale, and timezone. Record whether the iframe receives any supported public signal. If it does not, retain and document browser/standalone fallbacks; do not infer equality with the HA user preference.
6. Run component/browser/accessibility and visual-reference review at phone, tablet, and desktop sizes, light/dark, forced colors, reduced motion, 200% zoom, long/RTL text, and virtual keyboard. Record explicit reviewer approval or a divergence with rationale.

The [local Supervisor/App lab](../ha-app-lab.md) now proves Core-to-Supervisor Ingress session enforcement and proxy routing to `/health` and `/ready` on one disposable installation. It also records an authenticated Home Assistant App entry whose iframe stayed `about:blank` in the in-app browser. No App host-context message, Lit asset/deep-route behavior, or browser visual/accessibility approval was obtained. The [fixture review checklist](README.md) remains a starting point only.
