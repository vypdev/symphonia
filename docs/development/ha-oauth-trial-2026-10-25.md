# Installable OAuth research App

**Date:** 2026-10-25. **Issue:** [#26](https://github.com/vypdev/symphonia/issues/26).
**Status:** research artifact; no production authorization implementation.

The owner requested an installable test App and the simplest HTTPS option
after the [actual installation preflight](app-oauth-session-preflight-2026-10-25.md).
The separate [Symphonia OAuth Trial source](../../tools/ha_oauth_trial/README.md)
and [immutable artifact exporter](../../tools/prepare_ha_oauth_trial.py) provide
that preparation. The production App, runtime and permissions are unchanged.

## Selected trial topology

The owner's Chrome UI showed Nabu Casa remote access already enabled. Use its
existing HTTPS origin for the authenticated administrative panel. A separate,
opt-in Cloudflare Quick Tunnel runs inside the research App and connects only
to its callback listener on `127.0.0.1:8100`. Administration listens on 8099
behind Supervisor Ingress. No host ports, router forwarding or HA API access
are requested. The tunnel defaults off, boot is manual, and the process stops
after twenty minutes. One attempt per start expires after ten minutes.

Official [Cloudflare Quick Tunnel documentation](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)
reviewed on this date describes a temporary random HTTPS hostname without an
account or domain. Its hostname changes on restart, so register each trial's
exact callback in the dedicated Spotify test application. There is no uptime
guarantee; this is a test topology, not the selected production deployment.
Cloudflare terminates callback TLS and may observe the short-lived OAuth code
and state; it does not receive the PKCE verifier, provider tokens or HA session.
Opening this public route and installing the reviewed App require their
applicable action-time authorization before acting in the owner's Chrome UI.

The [Spotify redirect contract](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri)
requires matching registration and HTTPS outside literal loopback addresses.
The existing HA OAuth relay does not forward to this App-owned callback.
The native Spotify integration's registration and grant remain separate.

The owner's existing Terminal App was checked read-only in Chrome: curl,
sha256sum and mktemp exist, but `/addons` is not mounted. The preferred route
therefore uses the App store and the exact existing managed research branch,
with root `repository.json`; it does not widen Terminal privileges. Official
[repository documentation](https://contributors.home-assistant.io/apps/guides/repository/)
and [Supervisor 2026.10.3 discovery source](https://github.com/home-assistant/supervisor/blob/2026.10.3/supervisor/store/data.py)
confirm nested App discovery. The source branch is moving: verify its head
before installation and compare the private page's server hash with the
immutable exported manifest. Do not enable automatic updates for the trial.

## Artifact and security boundaries

The App directory contains four reviewed files: Dockerfile, JSON-compatible
`config.yaml`, `server.py`, and README. Both base images are multiarch and pinned:

| Component | Immutable image identity |
| --- | --- |
| Python 3.13 slim | `python@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962` |
| cloudflared 2026.10.3 | `cloudflare/cloudflared@sha256:faa8e0a1475f137c910be6025f43c8e4092fdd35461b31e19fd1390657a1ff39` |

Supervisor creates `/data/options.json` as root:0600. The first lab start
therefore refused setup under a preselected unprivileged container user.
The corrected entrypoint reads only that bounded regular non-symlink file,
clears inherited environment variables and irreversibly drops supplementary
groups, GID and UID to 10001 before opening listeners or starting a child.
It never changes filesystem ownership or reads HA configuration/credentials.
Options contain only the public test Client ID, management HTTPS origin and
tunnel opt-in. No grant material or browser session is persisted.

Ingress identity requires the actual Supervisor peer, one valid user ID,
Ingress path, HTTPS protocol metadata and an unambiguous validated Ingress
cookie. A keyed cookie fingerprint binds the Supervisor session; a separate
Secure/HttpOnly/SameSite=Strict cookie binds the browser; Origin and a separate
CSRF token protect mutations. The callback listener ignores all HA identity
headers. It stages a bounded code and never performs exchange. Finalization
through the initiating Ingress context consumes once, verifies profile,
refreshes once and checks the same immutable account, then discards references.

This profile names **Supervisor Ingress session** and **App browser session**
binding. Core login logout/revocation propagation is still `not_proven`.
Provider revocation remains separate from local disposal. Durable encrypted
tokens, backup/restore, broad provider capabilities and production release
gates are outside this disposable artifact.

## Dated lab evidence

The existing pinned Supervisor lab was resumed; no second container was
created. The trial was staged into a new dedicated local App directory after
checking that its destination was absent and its parent was not a symlink.
Supervisor installed it, applied synthetic options with the tunnel off,
rebuilt after the bounded entrypoint correction, and started it successfully.
The real service's `/proc/1/status` showed all four UID fields as 10001;
Docker host port bindings were empty. The embedded binary reported cloudflared
2026.10.3 without creating a tunnel.

| Core → Supervisor → trial App probe | Observation |
| --- | --- |
| No Ingress session | HTTP 401 |
| Internal session, HTTP protocol metadata | HTTP 403 |
| Internal session, synthetic HTTPS metadata | Root HTTP 200 |
| App cookie | Secure, HttpOnly and SameSite=Strict present |
| Start while tunnel disabled | HTTP 403, no provider request |

The probe created an internal **disposable Core** owner session and traversed
the actual Core/Supervisor proxy. Its HTTPS metadata was synthetic; it does
not prove browser TLS, Chrome iframe cookie behavior or the owner's login.
Only numeric statuses and boolean cookie properties were emitted, never user
IDs, cookies, Ingress route tokens or private URLs.

## Verification and live trial gates

[29 App tests](../../tests/test_ha_oauth_trial.py) cover actor/session/browser
separation, peer/header ambiguity, HTTPS, CSRF/Origin, exact callback host and
route, expiry, replay, concurrency, denial/cancellation, restart, bounded
options, token/scope/account checks, real loopback listener isolation and
permissions. [Three artifact tests](../../tests/test_prepare_ha_oauth_trial.py)
cover deterministic allowlisted archives, hash verification, moving-ref
rejection and refusal to overwrite existing output. These supplement the
previous isolated/provider experiments and unchanged production SDD budgets.

Before an actual provider trial: review the exported source revision and
manifest; stage without overwriting an existing source folder; install the
App; configure only the dedicated public Client ID and existing HA HTTPS
origin; verify private Ingress with the tunnel off; approve enabling the
limited tunnel; register its exact redirect; and run the
[16-case live matrix](app-oauth-session-preflight-2026-10-25.md#required-live-acceptance-matrix).
The [App procedure](../../tools/ha_oauth_trial/README.md) includes stop,
uninstall, redirect removal and dedicated-grant cleanup.

The package is preparation, not evidence of a public callback or real HA
session binding. Those remain pending until actually run and recorded.
The runtime and authorization SDDs remain Draft with unchanged blockers.
No accepted production architecture contract or ADR is changed by this trial.

Local verification passed **463 Python tests**, with **89%** combined
line/branch coverage against the unchanged 85% floor. Specification validation,
whitespace and manual catalog/SDD checks passed. The lab trial was explicitly
stopped; its fixed lifecycle output confirmed local credential disposal.
Real Chrome HTTPS remains pending: the browser policy rejected the value
returned by the masked remote-link copy control as an invalid URL. No
alternate egress route was attempted; the owner was asked to open the intended
HTTPS page manually. No trial App or public tunnel was installed/started on
the owner's instance during preparation.

Traceability: `SYM-SEC-001`–`SYM-SEC-007` cover the bounded PKCE, session,
replay/expiry and local disposal probes; `SYM-SEC-008`–`SYM-SEC-010` cover listener,
origin and redirect isolation; `SYM-HA-009` covers bounded actual Ingress
transport evidence. These results do not close the complete SDD budgets.
