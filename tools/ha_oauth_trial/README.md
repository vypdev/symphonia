# Symphonia OAuth Trial

Experimental, disposable Home Assistant App for the owner-authorized OAuth
research trial. This is separate from the Symphonia runtime. It does not
implement the Draft production authorization capability.

## Access and lifetime

- Administrator UI: Supervisor Ingress on port 8099, requiring the actual
  Supervisor peer, user identity, a valid forwarded Ingress session cookie,
  and HTTPS. Open through the installation's existing Nabu Casa HTTPS URL.
- Callback: only `GET /oauth/callback` on `127.0.0.1:8100` **inside this App**.
  It has no management handlers and ignores forwarded user/session headers.
- Optional Cloudflare Quick Tunnel connects only to that loopback callback
  listener. It is disabled by default. No host ports, router changes, host
  networking, privileged mode, config/media mounts or Home Assistant API
  privileges are requested. Cloudflared receives a minimal environment without
  Supervisor credentials. Its metrics listener is also loopback-only.
- Supervisor supplies `options.json` as root:0600. The entrypoint briefly
  reads only that bounded, non-symlink, non-secret file, clears inherited
  environment variables, then drops groups/GID/UID to 10001 before opening
  any listener or starting cloudflared. It does not change filesystem owners.
- One authorization attempt per App start. The attempt expires after ten
  minutes. The process, tunnel and all in-memory state stop after twenty
  minutes, including while idle. Boot mode is manual; do not enable watchdog
  or automatic startup for this trial.

Cloudflare terminates the public callback's TLS and can observe its temporary
OAuth code/state. The PKCE verifier and Spotify tokens are never sent through
that tunnel. The callback never exchanges the code on its own. It stages it
until the original authenticated HA actor, exact Supervisor Ingress session
and App browser cookie return through the private Ingress completion form.
The provider-side grant may survive local disposal; its revocation is separate.

## Install the reviewed artifact

The recommended route on the owner's installation is the Home Assistant App
store. Its existing Terminal App has no `/addons` mount; do not widen its
permissions. Add this **existing Action-managed research branch** as a custom
repository after reviewing the current source revision:

```text
https://github.com/vypdev/symphonia#chore/26-prove-spotify-oauth-feasibility-in-the-disposable-home-assistant-app-lab
```

Root `repository.json` makes the repository loadable. Supervisor discovers
Apps recursively, including this self-contained folder. Install only
**Symphonia OAuth Trial**, not the separate Symphonia scaffold also discoverable
there. Keep automatic updates off. Check the branch head immediately before
installation and compare the server SHA-256 displayed by the private App page
against the immutable export manifest. Any mismatch requires fresh review.
The branch is a moving ref, not an immutable pin; the reviewed commit and
runtime hash must be recorded for the actual trial.

An optional local-source route is available for installations that already
have a writable `/addons` mount:

The host-side `tools/prepare_ha_oauth_trial.py` creates a source archive,
SHA-256 manifest and staging script from an exact committed revision. The
script downloads only the four allowlisted files from immutable GitHub URLs,
verifies every digest, refuses an existing destination or symlinked `/addons`,
and creates only `/addons/symphonia_oauth_trial`. It reloads the store; it does
not install, start, configure or expose the App. Review the manifest and
script before running it in the existing Terminal & SSH App. If `/addons` is
not mounted there, stop and choose an explicit file-transfer route; do not
expand that App's permissions automatically.

After local staging, install **Symphonia OAuth Trial** from the local Apps store.
Keep the published Symphonia App and native Spotify integration separate.
Use these non-secret App options:

```yaml
client_id: <dedicated Spotify test application's public Client ID>
management_origin: https://<existing-private-HA-host>.ui.nabu.casa
tunnel_enabled: false
```

The management origin has no trailing slash or path. Client Secrets, tokens,
authorization codes, cookies and PKCE verifiers are not options. Default blank
options refuse startup rather than inventing a client or origin.

## Trial procedure

1. Review the exact artifact, permissions and Cloudflare exposure with the
   owner. Install only after the applicable action-time authorization.
2. Enter the dedicated Client ID and existing HA HTTPS origin. First start
   with `tunnel_enabled: false`, verify App discovery and private Ingress
   access, select **Verificar sesion privada**, require
   `private_context_verified: true`, and stop. This probe admits no OAuth
   attempt and makes no provider call or public listener.
3. After authorization for the limited public callback, set
   `tunnel_enabled: true` and start. Open the App over HTTPS. The private page
   shows the generated `https://<random>.trycloudflare.com/oauth/callback`.
4. Add that **exact** URI to the dedicated Spotify application's redirects.
   Do not change the native HA integration's application. Keep this App start
   alive: a new tunnel gets a new hostname and needs registration again.
5. Select **Autorizar Spotify**. The form opens Spotify in a separate tab,
   leaving the HA App tab available. Review only `user-read-private` consent.
   The provider returns to the App-owned callback through Cloudflare.
6. Return to the original HA App tab and select **Completar**. It verifies
   the original actor, Ingress session, browser cookie, Origin and CSRF token,
   then exchanges once, checks immutable profile identity, refreshes once and
   checks the same identity. Only safe result flags reach the page.
7. Record safe flags and versions, then stop the trial. No provider token is
   stored. A restart abandons a pending code rather than attempting recovery.
   If consent is denied, the state expires, verification fails or the result
   is unknown, restart with a fresh registered tunnel/attempt; do not replay.

This proves only the named App browser and Supervisor Ingress session
boundaries. Immediate revocation of the underlying Core login is explicitly
`not_proven`; never infer it from the forwarded user ID. A browser unable to
retain the Secure, HttpOnly, SameSite=Strict App cookie must fail completion.
Do not weaken cookie, Origin, peer or actor checks to make a trial pass.

Core overwrites the Ingress response's `Referrer-Policy` with `no-referrer`.
The private document therefore declares `same-origin` metadata before its
forms so Chrome retains the exact Origin for private POSTs. Cross-origin
requests still receive no Referer. The callback keeps `no-referrer`; it never
renders the private policy or an Ingress URL. A null Origin remains rejected.
Version `0.1.0-trial.1` lacked this document policy. Version
`0.1.0-trial.2` supplied it, but the owner's manual start still failed before
consent; the exact remaining gate is unknown. Version `0.1.0-trial.3` adds the
private session probe and allowlisted fixed rejection codes. These codes
never include request/cookie/CSRF/Origin values or raw exception text. They
are shown only for verified Ingress contexts or the actual Supervisor peer;
untrusted peers get a generic category. Public callback errors stay generic.
Do not activate the tunnel until the private probe passes. See the [dated result](../../docs/development/ha-oauth-trial-2026-10-25.md#owner-installation-and-first-https-trial).

## Stop and remove

Stop **Symphonia OAuth Trial** in its App page. This ends the public URL and
discards grants, verifiers, pending codes and browser-session references.
Uninstall it through Supervisor when no further research needs it. Keep a
reviewed source archive/manifest for reproduction; remove its local source
folder only after confirming its ownership and that the App is uninstalled.
Remove the temporary redirect from the dedicated Spotify test registration.
Remove that dedicated app's grant in Spotify Account Apps if provider-side
revocation is desired. Never revoke the app used by the native HA integration.

## Evidence and limits

The server suppresses request URLs, raw provider errors and cloudflared logs.
It prints only fixed lifecycle flags. Do not paste raw HA App info responses,
Ingress URLs, cookies, OAuth URLs, private instance URLs or provider responses
into public evidence. Record the source revision, image digests, public
scope, booleans, status codes and versions instead.

Run the deterministic suite with
`PYTHONPATH=src:. python3 -m unittest tests.test_ha_oauth_trial -v`.
Live deployment, Chrome cookies, public tunnel reachability, the 16-case live
matrix and real provider binding require their own dated results. A source
package or Docker build alone does not establish those claims. Production
encrypted storage, durable refresh, backups and release readiness remain open.

Official sources reviewed 2026-10-25:
[Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/),
[Spotify redirects](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri),
[HA Ingress](https://contributors.home-assistant.io/apps/guides/ingress/).

The review-only `0.1.0-trial.4` revision canonicalizes configured HTTPS ports to
match browser Origin serialization (default 443 omitted, other ports decimal).
Incoming Origin checks remain exact. It has not been installed or run on the
owner's HA; the earlier stopped trial and its historical results are unchanged.
The selected native companion design does not use this callback/tunnel trial.
