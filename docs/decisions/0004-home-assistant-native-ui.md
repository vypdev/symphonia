# ADR 0004: The App UI follows Home Assistant-native interaction and visual patterns

- **Status:** accepted
- **Date:** 2026-09-20

## Context

Symphonia's primary management surface runs inside Home Assistant through Ingress. A generic SaaS-style dashboard would make the App feel detached from its host and would force users to learn a second set of navigation, form, status, and feedback conventions.

The owner clarified that Symphonia's UI and components must be as close as practical to native Home Assistant, following the approach demonstrated by [`vypdev/homeassistant-gateway`](https://github.com/vypdev/homeassistant-gateway). The Gateway is useful dated implementation evidence: at commit [`1ed75be`](https://github.com/vypdev/homeassistant-gateway/tree/1ed75be9f8fabdab386db0fe4320cfb0f67d4f42) it uses a compatibility token layer, presentation-only primitives, a component catalog, responsive and visual tests, and committed Home Assistant visual references.

Home Assistant's official frontend remains the primary reference, but its built-in components are not a stable public dependency for an independently served App. Home Assistant's own 2026.4 developer notice warns custom-card authors that those component APIs may change and recommends independent components; the same churn risk applies more strongly to an App that would reach across its iframe boundary.

## Decision

Symphonia's App UI will be **Home Assistant-native-adjacent**: it will reproduce the host's current interaction model, information density, component families, terminology, theme behavior, responsive conventions, and restrained operational visual language as closely as practical without claiming to be part of the Home Assistant frontend.

Symphonia will own a small presentation-only compatibility layer for its component families and semantic design tokens. That layer will:

- follow official Home Assistant design guidance, design-portal examples, current frontend source, and dated reference captures;
- expose Symphonia-owned primitives for buttons, icon buttons, fields, selectors, check controls, tabs, cards, settings/list rows, status indicators, alerts, dialogs, progress, empty/loading states, tables, and responsive layout;
- consume public theme, locale, direction, safe-area, and Ingress context only when the supported Home Assistant contract exposes them, with deterministic standalone/browser fallbacks;
- keep application state, API calls, provider rules, and use-case orchestration outside presentation primitives; and
- remain independently deployable and testable without importing undocumented or private Home Assistant frontend modules.

Visual fidelity is a compatibility objective, not permission to copy unstable implementation details blindly. Semantic behavior, accessibility, current Home Assistant terminology, light/dark theme parity, mobile behavior, and state clarity take precedence over pixel identity to one release.

The frontend framework remains a separate implementation decision. A framework is acceptable only if it can satisfy the compatibility-layer, Ingress, accessibility, performance, catalog, and test contracts without coupling the domain/application core to Home Assistant.

## Consequences

Positive:

- the App feels coherent when opened inside Home Assistant;
- familiar controls and wording lower the learning cost;
- an owned compatibility layer isolates Symphonia from Home Assistant frontend churn;
- the same presentation package can render predictably in Ingress and standalone test/catalog contexts;
- dated references and visual tests make “looks native” reviewable instead of subjective.

Trade-offs:

- the component layer and visual reference set require ongoing maintenance as Home Assistant evolves;
- direct use of convenient Home Assistant internals is prohibited unless a later public, versioned contract justifies it;
- every supported release needs light/dark, narrow/wide, keyboard, accessibility, and Ingress-context evidence;
- pixel-level divergence may be necessary when accessibility, security, responsiveness, or an independent deployment boundary requires it.

## Rejected alternatives

### Generic product-branded SaaS dashboard

Rejected because it conflicts with the primary Home Assistant host experience and the owner's explicit direction.

### Import Home Assistant private components directly

Rejected as the default because the external component APIs are not a stable supported contract and current migrations can rename or replace controls between monthly releases.

### Freeze a pixel copy of one Home Assistant release

Rejected because it would age immediately, discourage semantic/accessibility improvements, and confuse resemblance with compatibility.

### Duplicate presentation behavior separately in every feature view

Rejected because inconsistent states, focus behavior, spacing, and responsive rules would undermine the native-adjacent goal and make upgrades unreviewable.
