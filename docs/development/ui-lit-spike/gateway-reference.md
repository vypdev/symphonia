# Gateway-informed Symphonia UI review map

**Reviewed:** 2026-10-02. **Gateway revision:** [`1ed75be`](https://github.com/vypdev/homeassistant-gateway/tree/1ed75be9f8fabdab386db0fe4320cfb0f67d4f42). **Status:** design evidence for an isolated, synthetic-data review fixture; no production UI or Home Assistant compatibility approval.

The owner asked Symphonia to follow the visual direction used by
`vypdev/homeassistant-gateway` while covering Symphonia's product journeys as
fully as the contracts permit. The pinned revision is the current `main` head
observed on the review date. Its [design rules](https://github.com/vypdev/homeassistant-gateway/blob/1ed75be9f8fabdab386db0fe4320cfb0f67d4f42/DESIGN.md),
[component catalog](https://github.com/vypdev/homeassistant-gateway/blob/1ed75be9f8fabdab386db0fe4320cfb0f67d4f42/docs/frontend-ui-catalog.md),
and dated [public Home Assistant captures](https://github.com/vypdev/homeassistant-gateway/tree/1ed75be9f8fabdab386db0fe4320cfb0f67d4f42/docs/ui-reference/home-assistant)
are comparative implementation evidence. Symphonia owns its components and
feature language; Gateway's MCP/client policies do not transfer to music flows.

## Visual and interaction translation

| Gateway evidence | Symphonia use | Constraint |
| --- | --- | --- |
| Quiet static canvas, opaque cards, subtle 1 px boundaries, restrained radius/elevation | One App-interior shell and bounded music/operation surfaces | Do not reproduce Home Assistant's outer sidebar inside Ingress |
| Flat tabs with a visible active indicator | Overview, Listening, Connections, Library, Matches, Copy, Activity | Preserve text, keyboard focus, selected semantics, and mobile access |
| Settings rows with icon, title, supporting text, status/action | Provider connection and playback source/output selection | Status cannot imply authorization or playback capability from provider type alone |
| Compact metric cards, result rows, status chips | Import freshness, match review, copy outcomes, operation history | Chips label facts; full recovery instructions stay in adjacent prose |
| Semantic alert, disabled/loading action, labelled form/control variants | Partial import, unavailable player, blocked copy, unknown provider write | Never report success from a browser event or enable a write in the fixture |
| Light/dark semantic tokens and consistent geometry | Independent browser fallback until a public host-context contract is verified | No private HA modules, parent DOM, or storage access |

Gateway's screenshots show a compact operational hierarchy rather than a
decorative dashboard. Its component catalog separates presentation primitives
from API/controller code; Symphonia's Lit review fixture follows the same
dependency direction without copying Gateway source or claiming parity with
every Home Assistant version.

## Product journey coverage for the review fixture

| View | Required reviewable facts | Safe fixture interaction |
| --- | --- | --- |
| Overview | Connection, last complete import, unresolved items, durable activity | Navigate to the relevant section |
| Listening | Explicit source, content, output, now playing, freshness and unsupported controls | Inspect selection and disabled reasons; no HA command |
| Connections | Access basis, account/health, capability and reconnect state | Inspect disclosure; no OAuth or credential entry |
| Library | Complete snapshot versus latest partial attempt, ordered playlists and unavailable items | Inspect retained state; no provider read |
| Matches | Per-occurrence ambiguity, evidence, and manual-decision need | Inspect candidates; no durable resolution write |
| Copy | Source/target/plan digest, ordered ready and non-ready occurrences, zero-write preview | Inspect blockers; confirmation stays unavailable |
| Activity | Queued/waiting/partial/confirmed/unknown outcomes and recovery | Inspect redacted status; no blind retry |

The fixture switches among synthetic scenarios and themes to inspect state
copy and layout. Those controls and local section navigation are real interactions; provider, copy,
authorization, and playback controls remain visibly unavailable until their
SDDs and server contracts permit an operational vertical slice. Every mock
record is invented and contains no user or provider secrets.

## Evidence required before product use

1. Accept a supported Home Assistant, browser, Companion App, and viewport matrix.
2. Verify the public Ingress base path, host properties, safe-area behavior, and deterministic theme/locale/direction/timezone fallback on that matrix.
3. Exercise component keyboard, focus, contrast, responsive, reduced-motion, long-text, and RTL behavior in real browsers; meet the UI SDD's 92-case budget.
4. Capture versioned official Home Assistant references and matching Symphonia screens, then obtain product/UX and accessibility review of visual parity and intentional divergences.
5. Promote the UI SDD to `Ready for implementation` only after its blockers clear; wire one authenticated feature view after the already stated owner approval is applied to a ready contract.

The [UI foundation SDD](../../../specs/home-assistant-native-ui.md) and
[feature SDDs](../../../specs/README.md) govern actual behavior. This map does
not replace their acceptance scenarios or authorize production frontend code.
