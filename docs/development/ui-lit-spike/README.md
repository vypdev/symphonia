# Isolated Lit/TypeScript/Vite build spike

This is **non-production RG-006 evidence**, not an App route, production component package, or SDD completion claim. It tests the owner-approved [ADR 0005](../../decisions/0005-lit-typescript-vite-ui.md) stack with synthetic UI data and no provider, Home Assistant, or Symphonia API access. The earlier [HTML/CSS review fixture](../ui-spike/README.md) remains the broader visual concept; this smaller spike verifies tooling and a presentation-only component boundary.

From this directory, run `npm ci --ignore-scripts`, `npm run check`, `npm test`, `npm run check-boundary`, `npm run build`, and `npm run verify-output`. CI repeats these checks. The lockfile pins the evaluated dependencies; npm is used **for this spike**, not chosen as the final package-manager policy. `vite.config.ts` emits relative asset URLs (`base: './'`) and `verify-output` checks them. This does not prove server routing, Ingress authentication, browser behavior, or Home Assistant visual parity.

The UI has one independently owned custom element, semantic tokens, native buttons, and explicit light/dark fixture control. Its imported `appearance.ts` is a pure fallback decision with deterministic tests. There are no API clients or host-private imports. Component-catalog breadth, WCAG/browser results, real base-path tests, HA context validation, and the 84-case SDD budget remain open.

Build size and dependency versions are recorded in [RG-006 host-context evidence](../ui-spike/host-context-evidence.md) after running the pinned build. Do not copy the package into the App before the UI SDD is `Ready for implementation` and the owner approves that stage.
