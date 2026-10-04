# Operational dashboard in the Home Assistant App

- Status: Implemented
- Date: 2026-10-04
- Catalog capability ID: `operational-dashboard`
- Owners: Symphonia maintainers
- Scope: show the App's persisted operational summaries and recent operation states through an admin-only Supervisor Ingress panel.
- Related requirements: `SYM-HA-009`, `SYM-SEC-008`, `SYM-UI-001`, `SYM-UI-002`, `SYM-UI-004`, `SYM-UI-005`, `SYM-UI-007`, `SYM-UI-008`, `SYM-UI-009`, `SYM-TEST-009`
- Related decisions/research: [UI foundation](home-assistant-native-ui.md), [ADR 0004](../docs/decisions/0004-home-assistant-native-ui.md), [ADR 0005](../docs/decisions/0005-lit-typescript-vite-ui.md), [local Ingress lab](../docs/development/ha-app-lab.md)
- Required review gates: product UX, architecture, testing, documentation, security/operations
- Open decisions blocking readiness: none within this read-only diagnostic scope
- Owner approval: explicit request to make the installed App UI operational on 2026-10-04.

## 1. Executive summary

The App opens to a live dashboard instead of a 404. It shows service health, queue, connection, library and identity counts, and recent operation states from existing redacted repositories. Refresh reloads authoritative data. It never suggests that unimplemented provider setup or playback is available.

```text
HA admin opens App -> Supervisor authenticates -> App validates proxy peer -> bounded diagnostic projection -> live cards and activity
```

## 2. Problem, current behavior, and evidence

### 2.1 Problem

An administrator cannot see anything useful after installing the App because `/` is 404.

### 2.2 Current behavior

The Python runtime serves `/health`, `/ready`, and `/version`; `RuntimeResources.diagnostics()` already returns bounded, redacted summaries. The local Supervisor probe proves authenticated routing but currently expects root 404. The isolated Lit fixture is synthetic and is not served.

### 2.3 Evidence and unknowns

- Repository evidence: [runtime/Ingress SDD](home-assistant-app-runtime-and-ingress.md), [UI specification](../docs/product/home-assistant-ui-specification.md), and [local lab](../docs/development/ha-app-lab.md).
- Official evidence: [App presentation](https://developers.home-assistant.io/docs/apps/presentation/) documents the Supervisor peer and `X-Ingress-Path`; [App configuration](https://developers.home-assistant.io/docs/apps/configuration/) documents `panel_admin`.
- Community evidence: [Gateway review](../docs/development/ui-lit-spike/gateway-reference.md) informs restrained visual hierarchy only.
- Unknowns outside this scope: complete supported browser matrix, public HA theme/locale transfer, provider authorization, playback, and full component catalog. This narrow dashboard uses browser fallbacks and does not claim the full UI foundation is ready.

## 3. Actors, surfaces, and terminology

| Actor | Goal | Entry point | Visible surfaces |
| --- | --- | --- | --- |
| HA administrator | Inspect actual App state | Open Web UI | overview, connections, library, activity, diagnostics |
| Operator | Diagnose failed or pending work | App panel | redacted status and recovery guidance |

“Snapshot” means a response computed from current persisted state. “Stale” means the last successful snapshot is retained after refresh failure.

## 4. Goals, non-goals, and fixed invariants

### 4.1 Goals

1. Root returns a meaningful, accessible screen through authenticated Ingress.
2. Every displayed count comes from durable runtime state, with explicit empty and unavailable states.
3. Refresh and navigation work without a root-path assumption.

### 4.2 Non-goals

1. Provider sign-in, import, copy, playback, mutation, or a standalone public listener.
2. Completion of the full UI foundation SDD or a general design-system catalog.

### 4.3 Fixed invariants

1. Dashboard and static assets are served only to the verified Supervisor Ingress peer; health checks remain usable locally.
2. The HTTP DTO contains no account names, credentials, payloads, checkpoints, event bodies, database paths, or Ingress tokens.
3. Client content is escaped by Lit and bounded by the server projection.
4. A refresh cannot overwrite a newer result or silently convert a failure to healthy.

## 5. Product journey

| Stage | Behavior | User effect |
| --- | --- | --- |
| Open | Authenticated Ingress loads relative assets | App title and loading state appear |
| Read | Dashboard GET returns current summaries | Counts and status replace loading state |
| Navigate | Local tabs select one section | Location remains clear without a new server route |
| Refresh | User requests a new snapshot | Fresh timestamp or an explicit stale/failure message |

## 6. Functional behavior and state model

### 6.1 Happy path

The UI requests `./api/dashboard` with same-origin credentials. The API checks the peer, asks the resource composition for diagnostics, projects an allowlisted DTO, and returns no-store JSON. Tabs navigate within the loaded snapshot. Refresh repeats the read and reports the time of the last successful fetch.

### 6.2 Alternative and boundary paths

- Without a Supervisor session, its proxy rejects the request before the App.
- Direct container-network requests to UI/API are denied even with forged Ingress headers.
- If stores are not ready, the API returns 503 with a safe status; the UI shows blocked recovery text.
- If refresh fails after a successful read, the last snapshot remains visible and both its message and heading status explicitly mark it stale.
- Unknown tabs select overview. Overlapping requests are fenced by a generation counter.

### 6.3 States

| State | Entry | Visible meaning | Next | Recovery |
| --- | --- | --- | --- | --- |
| loading | first GET | Reading stored state | ready, empty, blocked | automatic |
| ready | valid nonempty snapshot | Current persisted facts | refreshing, stale | refresh |
| empty | valid zero counts | No configured data yet | refreshing | consult setup guide |
| refreshing | user action | Previous facts retained | ready, stale | automatic |
| stale | subsequent GET fails | Last result is old | refreshing | retry or check App |
| blocked | first GET fails | State cannot be read | loading | retry, check App logs |

No write, cancellation, duplicate command, or partial external result exists in this read-only capability; operation status may itself report waiting/partial/failed facts.

## 7. Configuration contract

| Input | Type | Default | Range | Scope |
| --- | --- | --- | --- | --- |
| Ingress peer | fixed IP | `172.30.32.2` | no user override | App HTTP boundary |
| Theme | browser media preference | `auto` | light/dark browser result | client only |
| Locale | browser language | browser, then English | supported UI copy is English initially | client only |
| Polling | none | manual refresh | no background loop | client only |

No data migration is needed. Authorization and redaction are not configurable. Existing `SYMPHONIA_INGRESS_PATH` continues to constrain request routing; relative client URLs handle the Supervisor prefix.

## 8. Clean Architecture design

### 8.1 Responsibilities

| Boundary | Owns | Must not own/import |
| --- | --- | --- |
| Domain | existing operation and connection state | UI or HTTP |
| Application projection | allowlisted summary/view-model shaping | browser or database |
| Persistence adapters | current redacted diagnostics | HTML and styling |
| HTTP adapter | peer gate, headers and response transport; delegates public route selection, dashboard projection and static asset resolution to focused modules | business decisions |
| Lit presentation | `model.ts` owns validated snapshot state, `views.ts` owns pure section rendering, `main.ts` owns fetch/navigation events | SQLite and provider logic |

### 8.2 Contracts and trust

The DTO has version, generated time, ready, aggregate queue/connections/library/resolutions, and at most ten operation identifiers/types/states/timestamps. There is no new durable state. Refresh is an idempotent read. Peer IP comes from the socket, never an HTTP header. URL path and JSON are untrusted. Errors use bounded categories.

### 8.3 Executable constraints

Tests assert exact DTO keys and secret canary absence, direct-peer denial, relative asset paths, route fencing, and no infrastructure imports in application or the HTTP entrypoint. The production UI boundary check prevents outer-layer imports and browser I/O in model/views. The existing application dependency rules remain in force.

## 9. UI/UX and content contract

This first operational composition follows the [UI foundation](home-assistant-native-ui.md) hierarchy and Gateway-inspired shell, cards, tabs, status pills, and focus behavior. Its narrow scope intentionally precedes the full component catalog and visual matrix.

### 9.1 Information hierarchy

1. App title and actual service state.
2. Queue, connections, library and identity counts.
3. Recent operation states and refreshed time.
4. Recovery guidance and setup limitations.

### 9.2 Representative states

- Loading: “Loading stored status…”
- Empty/action required: “No connections recorded. Provider setup is not available in this build.”
- Ready: “Storage ready. Updated at [time].”
- Partial/stale: caution status “Snapshot stale” and “Could not refresh. Showing the last successful snapshot.”
- Blocked: “Status unavailable. Check that the App is running, then retry.”
- Completed operation: state text “Completed”; failed/waiting operations retain their actual state labels.

### 9.3 Accessibility and localization

Native buttons/links, skip link, labelled navigation, visible focus, live status region, dark/forced-color/reduced-motion CSS, and narrow layout are required. The interface ships English copy while date formatting uses browser locale; unsupported host theme/locale fields are never guessed. Lit text binding escapes values and operation strings are length-bounded before delivery.

## 10. Failure, recovery, and cleanup

| Condition | Impact | Retained facts | Retry | User action | Cleanup |
| --- | --- | --- | --- | --- | --- |
| Initial read fails | no state shown | none | manual | retry/check logs | abort request on disconnect |
| Refresh fails | snapshot stale | last safe snapshot | manual | retry | discard failed response |
| Resource unhealthy | no safe summary | server operations persist | manual | inspect App | no partial DTO |
| Unsupported asset/route | view cannot load | server state persists | no loop | reload/update App | no cache for HTML/API |

## 11. Security, permissions, and privacy

The panel remains admin-only via `panel_admin: true`; Supervisor authenticates Ingress. The App additionally accepts UI/API only from `172.30.32.2`. No cookie or header is treated as a separate credential. No mutation exists, so CSRF and replay cannot change state. The DTO uses exact allowlists and excludes raw diagnostic events, provider accounts and secrets. Responses set no-store, nosniff and a restrictive CSP for the HTML.

## 12. Observability and operational UX

The UI shows a last successful update time and sanitized readiness/operation states. HTTP logs remain quiet and never include route tokens. No automatic polling or repeated notification is emitted. `/health` and `/ready` remain the operator probes.

## 13. Compatibility, migration, rollout, and rollback

No schema or data change. The UI is built from a pinned lockfile and shipped as static assets in the App image; a prior image restores the prior HTTP surface without touching stored data. The local Supervisor lab validates 2026.9.4 Core and 2026.09.3 Supervisor; broader support remains a release gate in the foundation SDD. No irreversible effect exists.

## 14. Testing strategy and numeric budget

Minimum **18 distinct cases**: 4 DTO/redaction, 4 peer/path/header security, 3 client state/race, 3 layout/accessibility/browser behavior, 2 build/relative asset, 2 live Ingress/session. Deterministic fixtures use no provider calls. Live lab evidence supplements offline tests. The five production UI tests exercise empty, initial failure, stale, overlapping, and invalid responses; Python projection tests cover exact allowlists, unhealthy resources, bounded strings/counts, and the existing combined diagnostic source. HTTP/Ingress tests cover the peer gate, forged header, path/asset allowlist, missing session, and real proxy routes. Browser evidence covers light/dark, narrow width, navigation, refresh, and keyboard skip. The built asset is checked for reproducibility in CI. A failed refresh is a deterministic client test; it was not induced in the live administrator browser.

## 15. Documentation and discoverability

| Audience | Artifact | Content | Validation |
| --- | --- | --- | --- |
| User | [dashboard guide](../docs/development/operational-dashboard.md) | sections, refresh, limitations | link check |
| Setup owner | [lab guide](../docs/development/ha-app-lab.md) | rebuild and Ingress smoke | live probe |
| Operator | dashboard guide | stale/blocked recovery | error tests |
| Contributor | dashboard guide | DTO, build, boundaries | CI checks |

## 16. Acceptance scenarios

1. Given a logged-in HA administrator, Open Web UI shows the real operational dashboard.
2. Given no configured data, each section displays zero/empty truthfully and does not offer unfinished provider actions.
3. Given a queued or failed operation, activity shows its redacted identifier, type, state, and update time.
4. Given overlapping refreshes, only the latest response can change the screen.
5. Given a failed refresh, the last successful snapshot is labeled stale.
6. Given a direct network request or forged Ingress header, UI/API access is denied.
7. Given arbitrary non-root Ingress prefix, assets and API resolve within that prefix.
8. Given keyboard, narrow viewport, dark or forced colors, status and refresh remain usable.
9. Given a secret-bearing diagnostic payload, no secret reaches the DTO or rendered UI.

## 17. Requirements traceability

| Requirement | Owner | Verification | Documentation |
| --- | --- | --- | --- |
| `SYM-HA-009`, `SYM-SEC-008` | manifest/HTTP gate | peer/session tests | lab guide |
| `SYM-UI-001`, `SYM-UI-002`, `SYM-UI-004`, `SYM-UI-005` | Lit presentation | browser/semantic tests | dashboard guide |
| `SYM-UI-007`, `SYM-UI-008` | relative shell/fallback | Ingress and browser tests | dashboard guide |
| `SYM-UI-009`, `SYM-TEST-009` | projection/escaping | canary and build tests | dashboard guide |

## 18. Implementation sequence

1. Approve this bounded contract (owner request above).
2. Add redacted projection and security/path tests.
3. Add Lit package, build assets, and client state tests.
4. Integrate the runtime and disposable Ingress lab.
5. Document, review in browser, audit architecture, and publish with green CI.

## 19. Definition of Done

- [x] Root panel, relative assets and live API work through authenticated Ingress.
- [x] Direct access is denied and DTO redaction tests pass.
- [x] At least 18 distinct cases across projection, routing, client state, build, browser, and lab checks; the repository verification suite passes.
- [x] User/operator/contributor documentation and catalog evidence are current.
- [x] Browser visual and keyboard review is recorded in the lab guide.
- [x] GitHub Verify passed for the functional commit `557ceab` ([run](https://github.com/vypdev/symphonia/actions/runs/37224401052)); later refactors require their own green run.

## 20. References and decisions

Primary sources: official Home Assistant App presentation/configuration links above. Related SDDs/ADRs: UI foundation, App runtime, ADRs 0004/0005. Accepted: bounded read-only operational slice; rejected: synthetic data and unfinished actions. Full UI foundation and feature workflows remain separately gated.
