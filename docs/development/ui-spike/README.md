# Home Assistant-adjacent UI spike (review fixture)

This is a **non-production, synthetic-data-only** visual/interaction fixture for the [UI foundation SDD](../../../specs/home-assistant-native-ui.md). It is not served by the App, has no application/API calls, does not perform copy or connect providers, and does not select Symphonia's frontend framework. Open `index.html` locally to inspect the shell. The controls only change the local fixture view/theme.

Automated browser inspection of this local file was blocked by the current browser security policy on 2026-09-27. The repository tests check structure and isolation, but **no Symphonia screenshot, visual parity, responsive layout, or browser accessibility result has been approved**. A reviewer must perform the inspection below in an authorized environment; a future release cannot substitute static tests for it.

## Evidence and intentional choices

- Reviewed 2026-09-27 against the public [Home Assistant demo reference set](https://github.com/vypdev/homeassistant-gateway/tree/1ed75be9f8fabdab386db0fe4320cfb0f67d4f42/docs/ui-reference/home-assistant) captured 2026-08-05 (especially `menu-settings-light.png`, `menu-automations-light.png`, and `menu-automations-mobile.png`). Those captures are dated evidence, **not** a current supported-version matrix or proof of dark theme behavior.
- Compared with the [Gateway component catalog](https://github.com/vypdev/homeassistant-gateway/blob/1ed75be9f8fabdab386db0fe4320cfb0f67d4f42/docs/frontend-ui-catalog.md) at pinned commit `1ed75be9f8fabdab386db0fe4320cfb0f67d4f42`: opaque surfaces, quiet borders, flat selected navigation, compact status metadata, restrained action hierarchy. This fixture uses independently written CSS and native HTML controls; it does not copy Gateway components or assets.
- The top bar represents the **App interior**, not a replacement Home Assistant sidebar. Home Assistant owns its outer navigation; duplicating that shell inside Ingress would create a nested app. This is an intentional compositional distinction from Gateway's Home Assistant *reference* story.
- State copy follows the SDD: partial import identifies retained data and retry; copy preview never implies a write; completed/blocked operation examples show confirmed facts and recovery. All names/counts are fabricated.

## Inspection checklist

1. Open `index.html` and inspect Connections, Library, Copy, and Activity in a 1280×720 viewport and at 390×844. Check that the page does not scroll horizontally and the current section/action remains visible.
2. Toggle dark theme. Recheck status text, borders, focus rings, and contrast. Keyboard Tab through navigation, theme control, and demo actions; use Enter/Space where appropriate.
3. Zoom to 200%, inspect long text, and enable reduced motion/forced colors if available. These are exploratory checks, not a WCAG certification.
4. Compare light-mode density, card geometry, navigation indicator, controls, and status treatment with the pinned official-demo captures. Record any future divergence before treating this spike as an implementation input.

## Remaining gates

`RG-006` still needs a real supported Home Assistant/browser matrix, verified public host-context/Ingress contract, frontend/build selection, and approved capture/update/reviewer procedure. This spike does not satisfy the SDD's 84-case production test budget or authorize production UI implementation.
