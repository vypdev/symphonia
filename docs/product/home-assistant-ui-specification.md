# Home Assistant-native UI specification

**Status:** accepted product direction; implementation contract ready for specialist review
**Last reviewed:** 2026-09-20

## Purpose and scope

This document owns the cross-cutting product contract for Symphonia's web UI. Feature SDDs still own their information, actions, states, failures, and content; this specification defines how those surfaces fit Home Assistant visually and behaviorally.

The primary target is the authenticated Home Assistant Ingress panel. A standalone profile may use the same presentation layer, but it must not become a visually or behaviorally different product.

## Decision and evidence status

The owner has accepted the requirement that Symphonia's UI and components be as close as practical to native Home Assistant. [ADR 0004](../decisions/0004-home-assistant-native-ui.md) records the architectural consequences.

Evidence reviewed on 2026-09-20:

- official [Home Assistant frontend design guidance](https://developers.home-assistant.io/docs/frontend/design/) and [design portal](https://design.home-assistant.io/);
- official [frontend architecture](https://developers.home-assistant.io/docs/frontend/architecture/), which uses composable web components and unidirectional data flow;
- the official [`ha-card` source](https://github.com/home-assistant/frontend/blob/dev/src/components/ha-card.ts) as a current example of semantic tokens, opaque surfaces, border, radius, slots, and optional elevation;
- official [2026.4 component guidance](https://developers.home-assistant.io/blog/2026/03/25/frontend-component-updates-2026.4/), which warns custom-card authors not to depend on unstable built-in component APIs;
- official [2026.8 App/custom-panel guidance](https://developers.home-assistant.io/blog/2026/07/31/frontend-component-updates-2026.8/), including App-iframe safe-area propagation;
- `vypdev/homeassistant-gateway` commit [`1ed75be`](https://github.com/vypdev/homeassistant-gateway/tree/1ed75be9f8fabdab386db0fe4320cfb0f67d4f42), especially its [frontend direction](https://github.com/vypdev/homeassistant-gateway/blob/1ed75be9f8fabdab386db0fe4320cfb0f67d4f42/docs/frontend-design.md), [design system](https://github.com/vypdev/homeassistant-gateway/blob/1ed75be9f8fabdab386db0fe4320cfb0f67d4f42/docs/frontend-design-system.md), [UI catalog](https://github.com/vypdev/homeassistant-gateway/blob/1ed75be9f8fabdab386db0fe4320cfb0f67d4f42/docs/frontend-ui-catalog.md), [testing strategy](https://github.com/vypdev/homeassistant-gateway/blob/1ed75be9f8fabdab386db0fe4320cfb0f67d4f42/docs/frontend-testing-strategy.md), and dated [Home Assistant reference set](https://github.com/vypdev/homeassistant-gateway/tree/1ed75be9f8fabdab386db0fe4320cfb0f67d4f42/docs/ui-reference/home-assistant).

The official sources define the target. The Gateway is community implementation evidence, not a permanent Home Assistant guarantee and not a dependency selection.

## Terminology

- **Home Assistant-native-adjacent** means recognizably consistent with Home Assistant's current visual language and interaction model while remaining an independently served Symphonia UI.
- **Compatibility layer** means Symphonia-owned semantic tokens, presentation primitives, and layout helpers that isolate feature views from framework and host-specific details.
- **Component family** means one reusable semantic control or container category, not a one-off styled element.
- **Reference capture** means a dated screenshot of an official public Home Assistant surface used for human comparison, never as the only behavioral specification.
- **Visual parity** means comparable hierarchy, density, geometry, feedback, and theme behavior; it does not mean pixel equality with every Home Assistant version.

## Product principles

1. **Familiar before distinctive.** Use Home Assistant navigation, wording, control hierarchy, and status conventions before inventing a Symphonia-specific pattern.
2. **Operational before decorative.** The interface is quiet and information-led: opaque surfaces, moderate borders/radii, restrained elevation, and motion only where it explains state.
3. **Semantic before pixel-identical.** Accessibility, correct interaction, responsive behavior, and current host semantics outrank a frozen screenshot match.
4. **One compatibility layer.** Feature views compose approved families; they do not recreate buttons, fields, cards, dialogs, or status treatments ad hoc.
5. **Independent by construction.** Home Assistant private modules and undocumented DOM/CSS internals are not runtime dependencies.
6. **All product states are designed.** Loading, empty, ready, degraded, partial, waiting, action-required, blocked, failed, and completed states are first-class surfaces.

## Information architecture and shell

The Ingress panel must feel like one focused Home Assistant application, not a miniature operating system inside Home Assistant.

- A page has one clear title, an optional concise explanation, contextual actions, and a stable content region.
- Primary navigation uses a Home Assistant-like flat tab, list/settings, or compact mobile navigation pattern chosen by information depth; it does not mix several competing navigation systems.
- The current section is expressed textually and programmatically, not only by color or icon.
- Deep links and browser history work under a non-root Ingress base path.
- The shell reserves safe-area insets supplied by supported Home Assistant App iframe contracts and has a no-inset fallback.
- A narrow viewport changes layout and action placement without removing essential status, evidence, or recovery actions.

## Required component families

| Symphonia family | Home Assistant reference behavior | Required variants and states |
| --- | --- | --- |
| Page heading and toolbar | Settings and operational panel headings with contextual actions | title, description, leading/back action, primary/secondary actions, wrapping narrow state |
| Primary navigation/tabs | Flat HA tabs with a clear active indicator; compact mobile adaptation | selected, unselected, disabled, keyboard arrow/Home/End behavior, overflow/scroll |
| Card and section | `ha-card`-like opaque surface using semantic background, border, radius, spacing, optional restrained elevation | default, actionable, warning/blocked, disabled, nested section |
| Settings/list row | HA settings menu row with icon, primary text, supporting text, chevron/action | default, selected, disabled, destructive, multiline/narrow |
| Button | HA action hierarchy and size/density | primary/brand, secondary/neutral, destructive, success/warning where justified, text/link, icon-leading, loading, disabled |
| Icon button | MDI-style icon inheriting `currentColor` with accessible name and tooltip | default, hover/focus, pressed/toggled, disabled, destructive |
| Text/search/password field | Current HA form-field shape, label, help, validation, semantic form background | empty, populated, required, disabled, read-only, invalid, loading where applicable |
| Select/check/switch controls | HA-like choice hierarchy with explicit labels and descriptions | selected, mixed where applicable, disabled, invalid, grouped |
| Status chip/badge | Compact metadata only; text plus semantic tone | neutral, success/ready, warning/action-required, danger/blocked, unknown |
| Alert/feedback | Feedback adjacent to the affected scope | information, success, warning, error; polite/assertive announcement as appropriate |
| Dialog/adaptive confirmation | Labelled modal on wide screens and mobile-appropriate bounded surface | confirmation, destructive confirmation, loading, validation error, cancellation/focus return |
| Progress/loading/empty | HA-like progress and empty surfaces that explain what is happening | determinate, indeterminate with textual state, skeleton only when meaningful, empty with action, retryable error |
| Data list/table/result row | Dense operational data with semantic headings and bounded internal scrolling | populated, empty, loading, partial, row action, selected, responsive list alternative |
| Tags and evidence groups | Compact metadata, not primary actions | wrapping, overflow-safe, removable only when semantically an input |

Pills are reserved for compact status/metadata. Cards are not nested repeatedly for decoration. Destructive styling is reserved for destructive or irreversible effects. Provider artwork and branding may identify provider content, but must not replace Home Assistant interaction conventions.

## Tokens, themes, icons, and motion

The compatibility layer owns semantic aliases for canvas, surface levels, divider/border, primary and secondary text, brand/action, success, warning, danger, focus, typography, spacing, control/card radii, and optional elevation.

- When supported public Home Assistant context or iframe properties provide theme information, the UI maps them into the compatibility layer; it never reads Home Assistant private storage or traverses the parent DOM.
- Light and dark modes change tokens, not component geometry or information hierarchy.
- A deterministic fallback theme exists for standalone mode and for absent/malformed host context.
- Hard-coded colors are allowed only inside the token definition or for provider-owned brand artwork reviewed for contrast; feature components consume semantic tokens.
- Material Design Icons, or the selected compatible icon set, use consistent optical size and inherit `currentColor`; an icon never carries the sole accessible label.
- Permanent gradients, glassmorphism, decorative dot fields, ambient animation, and novelty effects are outside the accepted visual language.
- Motion is brief and state-explanatory; `prefers-reduced-motion` removes non-essential animation without hiding progress or focus.
- `prefers-contrast`/forced-colors behavior must preserve boundaries, focus, status text, and actions.

## Locale, direction, dates, and content

- The UI uses a supported public Home Assistant locale/timezone hint when available, then a browser/standalone setting, then English.
- Missing regional translations fall back from region to base language and then English.
- Component layout supports longer translated text, bidirectional provider metadata, and right-to-left document direction where the selected locale requires it.
- User-facing dates, numbers, durations, and time zones follow the resolved locale while durable values remain unambiguous UTC or typed quantities.
- Home Assistant terminology is preferred when it describes the same concept. Symphonia domain terms remain explicit where substituting a Home Assistant term would change meaning.
- Provider/user content is escaped, length-bounded, and never interpreted as HTML or Markdown.

## Accessibility and interaction

- The target is WCAG 2.2 AA for all supported flows.
- Every action is keyboard operable; focus is visible, ordered, and restored after dialogs or transient views close.
- Tabs, dialogs, tables, lists, fields, validation, progress, and live status use native semantics or complete ARIA patterns.
- Color, icon, position, animation, and shape are never the only carrier of status or required action.
- Loading updates are polite and non-disruptive; blocking/error transitions receive appropriate focus or announcement without repeatedly stealing focus during polling.
- Pointer targets and spacing remain usable on Home Assistant mobile/Companion App viewports and do not require hover.
- A disabled action explains its unmet prerequisite nearby or through accessible help; it is not a silent dead end.

## Responsive and Ingress behavior

Required reference viewports include at least a small phone, a common phone, tablet/narrow desktop, and wide desktop; exact browser support belongs to the release matrix.

- There is no unexpected document-level horizontal overflow.
- Tables, code, and diagnostic payloads may scroll only inside explicit bounded containers; essential actions remain reachable outside those containers.
- Multi-column content collapses predictably; result rows and form actions may stack without changing action order or semantics.
- Insets, browser zoom, large text, virtual keyboard, and narrow embedded-height cases must not cover primary actions or focused fields.
- Ingress routing, asset URLs, API URLs, deep links, refresh, WebSocket/SSE, and OAuth return/error views cannot assume `/`.

## State and feedback contract

Every feature view maps durable/application facts into this shared sequence:

1. current status;
2. completed facts;
3. what happens next;
4. required human action or an explicit statement that none is required;
5. impact and retained state; and
6. collapsed, sanitized technical evidence.

Errors follow `impact -> cause -> next action -> retained state`. Retry timing is absolute and localized when known. A spinner alone is never sufficient progress. A partial result is never styled or worded as success, and an external dependency outage is not presented as local data loss.

## Security and privacy boundaries

- Presentation primitives are pure with respect to provider calls, secrets, authorization, and domain decisions.
- The browser never receives provider refresh tokens, client secrets, raw cookies, or server-only diagnostic payloads.
- URLs from provider/user content use explicit allowed schemes and safe link attributes; untrusted content cannot choose navigation, callback, filesystem, module, or request destinations.
- Clipboard/download actions preview and label the bounded, sanitized content they expose.
- Visual snapshots, component fixtures, translations, and reference captures contain synthetic or public demonstration data only.

## Component catalog and visual reference policy

A component family is not ready until its catalog demonstrates:

- normal, disabled, loading, empty, invalid/error, and destructive variants where applicable;
- light and dark themes;
- keyboard focus and visible focus treatment;
- narrow and wide layouts plus long/translated content;
- accessibility inspection with no known critical/serious violation; and
- deterministic fixtures without network, Home Assistant instance, real account, or secret.

The project keeps a dated visual reference manifest pointing to official Home Assistant public-demo or design-portal surfaces and records the Home Assistant version/date, viewport, theme, provenance, and reviewer. Official source and documentation resolve ambiguity; screenshots do not define hidden behavior.

Visual snapshots are reviewed evidence, not self-approving output. A generated baseline change requires a human explanation of whether it follows Home Assistant evolution, fixes a defect, or intentionally diverges for accessibility/product reasons.

## Requirements

- **SYM-UI-001:** The primary App UI MUST be Home Assistant-native-adjacent in information hierarchy, terminology, density, component geometry, feedback, and responsive behavior, as defined by dated official references.
- **SYM-UI-002:** Feature views MUST compose an owned presentation-only compatibility layer and MUST NOT import undocumented/private Home Assistant frontend modules or depend on parent DOM/CSS internals.
- **SYM-UI-003:** The compatibility layer MUST provide the component families and required variants in this specification; one-off controls duplicating an existing family require a documented exception.
- **SYM-UI-004:** Light, dark, high-contrast/forced-colors where supported, and reduced-motion behavior MUST preserve semantics, focus, status, and usable actions.
- **SYM-UI-005:** Every user-facing capability MUST render loading/pending, empty where applicable, ready, degraded/partial, action-required, failed/blocked, and completed outcomes that exist in its SDD using text in addition to color or iconography.
- **SYM-UI-006:** The UI MUST meet WCAG 2.2 AA for supported flows and MUST provide keyboard operation, visible focus, correct control semantics, focus management, and bounded live announcements.
- **SYM-UI-007:** The UI MUST work under an arbitrary non-root Ingress base path and MUST adapt to supported safe-area, narrow/mobile, zoom, long-text, and embedded-height conditions without hiding essential state or actions.
- **SYM-UI-008:** Theme, locale, direction, timezone, and safe-area context MUST use supported public Home Assistant/App contracts when available and deterministic browser/standalone fallbacks otherwise; private Home Assistant storage/DOM access is prohibited.
- **SYM-UI-009:** Provider, user, localization, and diagnostic content MUST be escaped, length-bounded, overflow-safe, and non-executable; secrets and unrestricted raw payloads MUST be absent from UI state, fixtures, snapshots, clipboard, and downloads.
- **SYM-UI-010:** Every public component family MUST have a deterministic catalog covering its applicable variants, themes, focus, accessibility, and responsive states before feature views adopt it.
- **SYM-UI-011:** Release evidence MUST include behavioral, accessibility, responsive, and reviewed visual comparison against a dated official Home Assistant reference manifest; snapshot regeneration alone is insufficient approval.
- **SYM-UI-012:** Application/API/domain state and use-case orchestration MUST remain outside presentation primitives, and the UI MUST treat persisted application state rather than transient browser events as authoritative.
- **SYM-UI-013:** Standalone and Ingress profiles MUST share component and feature semantics; host context MAY change tokens, navigation integration, and authentication framing but MUST NOT create a second product behavior.
- **SYM-UI-014:** Decorative effects MUST NOT compete with operational status, evidence, or actions; permanent ambient gradients, glassmorphism, decorative animation, and novelty backgrounds are not part of the accepted visual language.
- **SYM-UI-015:** Supported Home Assistant/frontend compatibility MUST be versioned and revalidated when official component, token, App-iframe, or safe-area contracts change.

## Exceptions and review

A deliberate divergence from current Home Assistant behavior must record:

1. affected component/view and Home Assistant reference;
2. accessibility, security, product, or technical reason;
3. user-visible consequence;
4. fallback and compatibility impact; and
5. approval in the applicable SDD or ADR when the divergence is durable.

Provider branding alone is not an exception. A future public, versioned Home Assistant component package may justify direct reuse, but adoption requires a compatibility/rollback review rather than bypassing this contract.
