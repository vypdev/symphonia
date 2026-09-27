# ADR 0005: Use Lit, TypeScript, and Vite for the App presentation layer

- **Status:** accepted
- **Date:** 2026-09-27
- **Scope:** future Symphonia web UI and component catalog; not the Python/domain core

## Context

[ADR 0004](0004-home-assistant-native-ui.md) requires an independently served, Home Assistant-native-adjacent App UI with a Symphonia-owned presentation-only compatibility layer. The owner explicitly approved Lit + TypeScript + Vite on 2026-09-27 after reviewing the isolated UI fixture and the approach of `vypdev/homeassistant-gateway`.

Lit provides standards-based custom elements and reactive templates. TypeScript can type component inputs and host-context boundaries. Vite can build browser-resolvable static assets; it does **not** by itself solve arbitrary Ingress base paths, session/authentication, localization, safe areas, or visual parity. The [Gateway's pinned frontend](https://github.com/vypdev/homeassistant-gateway/tree/1ed75be9f8fabdab386db0fe4320cfb0f67d4f42/frontend) is implementation evidence, not a library to copy or an authority for Symphonia's behavior. [Lit documentation](https://lit.dev/docs/components/overview/) and [Vite production build documentation](https://vite.dev/guide/build.html) are the primary tooling references.

## Decision

When the [UI foundation SDD](../../specs/home-assistant-native-ui.md) becomes `Ready for implementation`, the production presentation package will use **Lit 3, TypeScript, and Vite**, subject to a reproducible lockfile and the then-supported versions. Lit component primitives will be presentation-only; feature controllers and API clients remain outside the public component package. The built UI will be independently served inside Home Assistant Ingress and use the same feature/component semantics in a standalone profile.

The implementation will not import private Home Assistant frontend modules, traverse the parent DOM, or assume Home Assistant theme/locale data is forwarded to App iframes. A validated public host-context adapter and deterministic browser/standalone fallbacks remain separate contracts. The App's parent owns the Home Assistant shell; Symphonia owns only its interior navigation and content.

This decision selects a framework/build direction, **not** a package manager, visual baseline, supported HA/browser matrix, validated host-context protocol, or permission to begin production UI. `RG-006` and the SDD readiness/owner-approval gates still apply. If bundle cost, browser support, accessibility, or Ingress compatibility cannot be demonstrated, a new ADR must supersede this one.

## Consequences and verification

- Favor native HTML semantics within Lit templates; component encapsulation must not hide labels, focus, or announcement behavior.
- A single public UI entry point, dependency-direction checks, deterministic catalog fixtures, type checking, browser/a11y tests, and reviewed visual references become release evidence.
- Vite output must work below arbitrary non-root Ingress prefixes for assets, navigation, refresh, API calls, and any push transport. Hash routes in the current static fixture are not proof of this.
- Build size and first meaningful render on a modest Home Assistant device must be measured before an implementation-ready matrix is accepted; no performance claim is made by this ADR.
- Dependency versions and license/security review are performed when the package is created; Gateway's versions are not inherited silently.

## Alternatives considered

- **Continue with plain HTML/CSS/JS:** suitable for the isolated review fixture, but does not supply the agreed typed reusable component package and catalog architecture for the full UI.
- **Use Home Assistant's private built-in components:** rejected by ADR 0004 because their external API and iframe availability are not a stable App contract.
- **Use another SPA framework:** not ruled out technically; the owner chose Lit's web-component approach for alignment with the Gateway pattern. A future evidence-based reversal would require a superseding ADR.
