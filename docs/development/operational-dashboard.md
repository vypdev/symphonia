# Operational dashboard

The Symphonia App opens an administrator dashboard inside Home Assistant's **Open Web UI** panel. It reads persisted state from the running App. The sections show service readiness, queue state, connection counts, library projection counts, identity-decision counts, and recent operation states. **Refresh** requests a new snapshot; the displayed update time changes only after a successful read.

This first view is read-only. Provider connection, import, playback, and copy controls are not available yet. Empty counts describe current stored data and do not imply that external providers were checked. The full UI foundation remains under review in [its SDD](../../specs/home-assistant-native-ui.md); this [dashboard contract](../../specs/operational-dashboard.md) is a bounded operational slice.

## Recovery

- **Loading:** wait for the first request. If it does not finish, reload the App panel.
- **Status unavailable:** check the App state in Home Assistant, then try **Refresh**. `/health` and `/ready` are operator probes inside the App network.
- **Showing last successful snapshot:** the latest refresh failed. The figures are old; try again or check App logs. Running operations continue in the server.
- **No connections recorded:** no connection is stored. Provider setup is not yet supported by this build.

## Implementation and verification

The server projects an allowlisted, redacted response at `./api/dashboard`; it never returns operation payloads, event bodies, account identifiers, database paths, credentials, or Ingress tokens. Static assets and the dashboard API are available only from the verified Supervisor peer. Supervisor authenticates the Ingress session and the App panel is administrator-only. The browser uses relative asset/API URLs so arbitrary Ingress prefixes work.

The UI source is in [`ui/`](../../ui/) and uses a pinned Lit/TypeScript/Vite build. Run `npm ci --ignore-scripts`, `npm run check`, `npm test`, and `npm run build` there. The build writes versioned static assets to `src/symphonia/runtime/ui_assets/`, which are included in the App image. Rebuild the local App with `python3 tools/ha_app_lab.py up`, then run `python3 tools/ha_app_lab.py ingress-smoke`. The regular Python suite and GitHub Verify workflow also check the projection, access boundary, and assets.
