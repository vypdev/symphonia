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

[32 App tests](../../tests/test_ha_oauth_trial.py) cover actor/session/browser
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

The initial package was preparation only. The subsequent owner-installation
trial below proves bounded HTTPS reachability, but real provider return and
session-bound finalization remain pending.
The runtime and authorization SDDs remain Draft with unchanged blockers.
No accepted production architecture contract or ADR is changed by this trial.

Local verification passed **463 Python tests**, with **89%** combined
line/branch coverage against the unchanged 85% floor. Specification validation,
whitespace and manual catalog/SDD checks passed. The lab trial was explicitly
stopped; its fixed lifecycle output confirmed local credential disposal.
During preparation, real Chrome HTTPS remained pending: the browser policy rejected the value
returned by the masked remote-link copy control as an invalid URL. No
alternate egress route was attempted; the owner was asked to open the intended
HTTPS page manually. No trial App or public tunnel was installed/started on
the owner's instance during that preparation phase. The owner subsequently
supplied the exact HTTPS URL and authorized the bounded installation/trial.

Traceability: `SYM-SEC-001`–`SYM-SEC-007` cover the bounded PKCE, session,
replay/expiry and local disposal probes; `SYM-SEC-008`–`SYM-SEC-010` cover listener,
origin and redirect isolation; `SYM-HA-009` covers bounded actual Ingress
transport evidence. These results do not close the complete SDD budgets.


## Owner installation and first HTTPS trial

The owner explicitly authorized installing revision
`4a42e48faa896a4d5fff8d4906a2021f971a7c64` and running the callback-only tunnel
for at most twenty minutes. The local and remote branch heads matched that
revision immediately before installation. Chrome added the managed branch
repository and Supervisor installed **Symphonia OAuth Trial 0.1.0-trial.1**.
Boot, watchdog and automatic updates remained off.

The first start used the dedicated public test Client ID, the owner's existing
HTTPS management origin and `tunnel_enabled: false`. The real authenticated
Ingress iframe rendered the private App page. Its server SHA-256 matched the
immutable export manifest:
`fac77d524ffedda8cc8682e9f450455e8a73d814b35b170cf44a94d670021c33`.
No browser cookie or HA credential value was extracted.

The App was stopped, then started with the approved tunnel enabled at about
08:58 UTC. Chrome reached its generated HTTPS callback with trusted TLS;
a callback without correlation, `/` and `/complete` all returned the fixed
callback rejection instead of management UI. The exact temporary redirect
was registered in the dedicated Spotify development app. No native HA
Spotify registration or grant was changed.

**The real provider flow did not pass.** Selecting **Autorizar Spotify**
returned the App's fixed rejection before Spotify consent. Reloading the
private form and opening it as a complete Ingress tab also failed. The private
report remained `register_callback_then_start`: no authorization attempt was
admitted and no Spotify token exchange or refresh was performed by this App.
A narrowly inspected diagnostic POST displayed `Origin: null`; no cookies,
CSRF values or full request headers were copied into evidence.

[Core 2026.10.3 header middleware](https://github.com/home-assistant/core/blob/2026.10.3/homeassistant/components/http/headers.py)
overwrites the upstream `Referrer-Policy` response header with `no-referrer`.
The trial had set its private response header to `same-origin`, but had no
corresponding document metadata. This suggested a possible mechanism, not an
established cause of the real HA rejection: the exact failure category of the
first generic rejection was not logged. Fetch's
[Origin-header algorithm](https://fetch.spec.whatwg.org/#append-a-request-origin-header)
does apply referrer policy to certain non-CORS, non-GET/HEAD requests, so
`no-referrer` can serialize their Origin as `null`. That rule and the isolated
fixture do not establish which condition caused the earlier HA failure.
A separate Chrome loopback fixture, without HA/Spotify data, reproduced the
browser behavior while keeping the HTTP header fixed at `no-referrer`:

| Synthetic browser case | `origin_exact` | `origin_null` |
| --- | --- | --- |
| Response header only | false | true |
| Private document `<meta name=referrer content=same-origin>` | true | false |

Version **0.1.0-trial.2** adds that metadata only to the private management
page. It retains exact Origin and CSRF validation, including rejection of
`null`; callback responses retain `no-referrer`. The new HTTP regression
parses the served form, rejects a null-origin start, accepts the exact-origin
start and makes no provider call. This is a prepared fix, not a passing real
HA/Spotify result; updating/running the revised research artifact needs its
applicable installation authorization.

The first App/tunnel was explicitly stopped before the 09:08:21 UTC public
closure check, within eleven minutes. Supervisor showed **Detenido**, the public hostname returned
Cloudflare tunnel error 1033, `tunnel_enabled` was restored to false, and the
temporary Spotify redirect was removed and verified absent. The installed
App is retained stopped for the corrected trial. Local grants were never
created in this run; provider revocation was not performed. The earlier
separate loopback grant proof remains separate evidence.

This live run partially exercises matrix cases 1/2 (callback reachability
from the current Chrome network, no independent off-LAN browser), 10 (GET
route isolation) and 16 (stop and temporary-redirect cleanup). Initiating
session completion, real App exchange/refresh, other users/browsers,
revocation, negative callback correlation, concurrency and the rest of the
16-case matrix remain unproven on the owner's installation.


The corrected revision passed **464 Python tests** (30 trial-App and three
exporter tests included), with **89%** combined line/branch coverage against
the unchanged 85% floor. Specification validation, whitespace and manual
catalog/SDD consistency checks passed. Its local aarch64 Docker image built
successfully as
`sha256:643ac21513635915176244fd9c83830d306dd9c17aab8bfd90025122b217434f`.
This build does not establish the revised App's real Ingress/provider flow.


## Corrected owner trial and remaining private-context blocker

The owner approved revision `8653e4db37a0b660386f9d16d0794ce76fbbbf77`
and version **0.1.0-trial.2**. The remote head matched immediately before
updating. Supervisor installed that version, and the tunnel-disabled HTTPS
Ingress panel displayed the expected server SHA-256:
`55c4affc5448b6c19a6254fdabd10c5f5f6949a64337d406c62041865f79b745`.
The revised source also passed GitHub Verify
[run 40179748250](https://github.com/vypdev/symphonia/actions/runs/40179748250).

A new tunnel started at about 10:59:47 UTC. Its temporary redirect was
registered in the dedicated Spotify app; a fresh `/complete` GET on the
public callback origin returned the generic callback rejection. A transient
Spotify dashboard save error was resolved by reloading the form and verifying
the saved URI. No Client Secret was viewed.

The automated start opened a tab without an observable valid URL. Browser
policy blocked observation; automatic review also rejected acquiring that
tab, requiring manual intervention. No blocked popup was inspected through
another surface. The owner requested a separate work group; **Symphonia OAuth**
was created with new HA and Spotify tabs. The new HA context was rejected;
its precise identity/session category was not recorded. A disposable restart
restored the private panel, replaced the temporary redirect and stayed inside
the original twenty-minute exposure window. The owner then manually selected
**Autorizar Spotify** and reported the same fixed **Trial action rejected**
message. This is a failed real start, not a successful provider callback.

The previous inference about `Origin: null` is insufficient to explain this
remaining failure. A second synthetic Chrome fixture added the actual trial
CSP, a same-origin iframe and `target=_blank`. It observed exact Origin,
single Origin/Content-Length headers, the expected content type and form,
no Transfer-Encoding and a synthetic App cookie. This validates only that
fixture. It does not prove the actual HA proxy headers or cookies, whose
values were not extracted.

The App was stopped before the 11:14:01 UTC closure check, within fifteen
minutes of the original start. Supervisor showed **Detenido**, the final
public hostname returned Cloudflare 1033, both trial redirect registrations
were removed/replaced and the dedicated app ended with its original loopback
redirect only. `tunnel_enabled` was restored to false. No successful App
provider exchange, refresh, callback correlation or bound finalization was
observed. Provider and Core-login revocation remain untested.

Version **0.1.0-trial.3** is prepared to diagnose the remaining gate privately.
**Verificar sesion privada** checks the same actor/Ingress/browser/Origin/CSRF
boundary without a tunnel, provider call or OAuth-attempt admission. A success
adds `private_context_verified: true` for that exact App browser session; failures expose/log only fixed codes
from a closed allowlist, with generic fallback for unknown exceptions and
untrusted peers. Origin and CSRF rejection codes are distinct; their checks
are unchanged. Public callback responses remain generic. Install/run of this
new revision requires its applicable action-time approval. The tunnel must
stay off until the private check passes.

The 16-case matrix and production SDD statuses/blockers remain open. Real
callback-only HTTPS reachability and install/hash checks passed; real
session-bound provider completion has still not passed.


The prepared diagnostic revision passed **466 Python tests**, including 32
trial-App and three exporter tests. Combined line/branch coverage is **89%**
against the unchanged 85% floor. Specification validation, whitespace and
manual SDD/catalog consistency checks passed. Its aarch64 Docker build is
`sha256:6a302bad0c800812eec2fd30110cff4fd6a808be9ccb997c22bc0177a9050aeb`.
The subsequent owner run below exercises the private probe. Neither the
synthetic iframe success nor these tests establish real Home Assistant
session-bound OAuth completion.

## Private context verified on the owner's installation

The owner approved revision `ad7328ac3011aab8e1dae0e172543e6f117aef96`,
version **0.1.0-trial.3**, with a tunnel-disabled private check first and a
conditional callback tunnel of at most twenty minutes. The remote head
matched before updating. Supervisor installed trial.3 and its real Chrome
Ingress page displayed the expected server SHA-256:
`60e46805208a8f6a5e4467943c47e5e9be4391f55b9b211d30ba1f3d4c6cca08`.

**Verificar sesion privada passed with the tunnel off.** The page reported
`private_context_verified: true` and `result: tunnel_disabled`. This exercises
the exact actor, Ingress-session fingerprint, App cookie, Origin and CSRF
checks on the owner's browser; it does not establish Core-login revocation.

After stopping, enabling the approved callback option and restarting at
about **11:32:56 UTC**, the same private check passed again. The generated
exact redirect was saved and verified in the dedicated Spotify application.
**Autorizar Spotify was admitted**: refreshing the original App page showed
`waiting_for_spotify` with the private-context flag still true. Unlike the
two earlier runs, this run establishes successful private authorization-start
admission. The precise earlier generic rejection remains unidentified.

The new consent tab initially had no valid URL available to browser control;
it was not inspected through another surface. Manual handoff was requested.
A concurrent public `/complete` GET probe returned the expected generic
callback rejection and was then closed because it could confuse that handoff.
The owner's first reported identical error cannot safely be attributed to
the actual provider return. No successful callback, exchange, refresh or
bound completion was observed. The owner then questioned the tunnel topology;
the attempt was stopped for that design discussion rather than treating the
incomplete handoff as a successful or definitively failed provider callback.

Supervisor showed **Detenido** and the public hostname returned Cloudflare
1033 by **11:39:53 UTC**, less than seven minutes after starting. The option
was saved back to `tunnel_enabled: false`; Spotify's saved redirects were
verified to contain only the original loopback URI. The App remains installed
and stopped, with boot, watchdog and automatic updates off. No native Spotify
integration was changed. Provider revocation was not performed.

The 16-case matrix still needs actual callback correlation and initiating
session finalization. These bounded successes do not change either Draft SDD,
the production callback direction, token-storage decisions or readiness gates.

## PR review follow-up: canonical management ports

The prepared `0.1.0-trial.4` source canonicalizes configured HTTPS ports to browser Origin serialization: explicit 443 is omitted and non-default ports use decimal form without leading zeroes. Received Origin and CSRF checks remain exact. Three new cases prove default-port private checks, non-default port isolation and decimal canonicalization without mutating the input configuration. The complete PR suite passes 483 tests at 89% coverage.

This correction does not identify the cause of the earlier owner-instance rejection. Trial.4 has not been installed, started or authorized against Spotify on the owner instance; the previous research App remains stopped. The selected native OAuth companion does not use this direct-callback/tunnel artifact.

## PR review follow-up: Ingress paths and opaque client IDs

Prepared trial.5 renders form actions and the refresh link under the server-validated Ingress base path. The rendered-form test resolves every action from document URLs both with and without a final slash and confirms the same App token is retained. It does not retrospectively establish the cause of an earlier owner-instance rejection.

Both callback research tools now accept a bounded opaque printable-ASCII public Client ID and encode it as one parameter. The 1–256 character limit is a tooling bound; it is not claimed as a Spotify format guarantee. [Spotify application documentation](https://developer.spotify.com/documentation/web-api/concepts/apps) identifies the public client identifier; [OAuth 2.0 section 2.2 and Appendix A.1](https://www.rfc-editor.org/rfc/rfc6749#section-2.2) define its role and syntax. Uppercase/reserved-character IDs retain the exact configured redirect and reach the fake exchange; empty, control/non-ASCII, wrong-type and oversized values fail before I/O. No non-hex Spotify registration or new live call was used.

The full PR suite passes **487 tests, no skips, and 89% coverage**. Trial.5 is prepared only; the owner App remains stopped and the selected native companion direction is unchanged.

## PR review follow-up: absolute parsing deadline

Prepared trial.6 adds a fixed two-second deadline for headers and POST body parsing. A socket watchdog shuts down a connection that keeps trickling bytes, releasing the synchronous listener; parsing completion cancels it before authorized provider work, which retains the existing per-request provider deadlines. Incomplete declared bodies are rejected. Loopback regressions cover trickled headers allowing a subsequent callback request, truncated bodies refusing private actions and provider work legitimately outlasting the parsing window. No tunnel or owner-instance run was performed.

A separate review alert claiming denial skipped cleanup was a false positive: the denial return was already inside the try/finally that clears both cookie and PKCE verifier. Its existing test already checked both fields; added assertions verify the truthful erasure result and denied replay. The implementation was not changed to satisfy that incorrect alert.
