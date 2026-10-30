# Home Assistant OAuth setup and recovery — design preview

**Status:** proposed UX/operator procedure, 2026-10-25. The production auxiliary
integration does not exist yet. Do not install a package, change HA or reopen the research
tunnel based on this preview. See the [SDD](../../specs/home-assistant-oauth-companion.md)
for readiness gates and the [RFC](../architecture/home-assistant-oauth-companion-rfc.md)
for trust/recovery details.

The separate [native validation trial](../../specs/native-oauth-validation-trial.md)
has its bounded contract and [current-Core hook evidence](../development/native-oauth-trial-hooks-2026-10-30.md).
It remains under maintainer review. Its package tests and bounded owner-browser
OAuth, restart, refresh/account match and retirement have passed; see the
[dated report](../development/native-oauth-trial-acceptance-2026-10-30.md). Its
[preparation gates](../development/native-oauth-trial-preparation.md) preserve
exact-package review before any owner installation; this production preview
does not become installable through that separate design review.

The [laboratory validation](../development/ha-oauth-companion-lab-2026-10-25.md)
now proves some mechanics, not a released package. It confirms that private
HA file permissions alone do not encrypt a key; unprotected backups can retain
plaintext. App key exclusion works, but restoration without that key leaves the
fixture locked. [ADR 0008](../decisions/0008-install-local-oauth-keys-and-backups.md)
selects automatic startup using private local keys and encrypted HA backups.
The final reset/rotation/publication implementation still needs proof.

## Intended normal setup

1. Install the reviewed Symphonia App and auxiliary custom integration from
   their eventually documented releases. They are separate artifacts; custom
   integration distribution/HACS eligibility is not selected or promised yet.
2. Open the App through admin-only Ingress and choose **Pair Home Assistant**.
   In HA **Settings → Devices & services → Add integration → Symphonia**, enter
   the internal App alias and temporary pairing challenge, then compare the
   fingerprint. A mismatch stops setup. Pairing authorizes OAuth only.
   The pair creates one HA entry; its native reconfigure flow handles provider
   connections, and native reauthentication handles reconnects. Exact labels
   remain subject to the supported-HA-version review.
3. Create/use a dedicated Spotify developer application. Register exactly
   `https://my.home-assistant.io/redirect/oauth`. Enter its public Client ID in
   the native Symphonia flow. The initial PKCE-only read profile has no Client
   Secret field. Do not paste tokens or copy another integration's credentials.
4. Review requested functional access, account prerequisites and grant ownership.
   Select **Connect Spotify**, consent on Spotify, then return to the HA flow.
5. Confirm linking as the administrator who started the flow. The callback alone
   has not connected anything. Wait for the App to verify account/scope and
   show a result; open Symphonia to see the connection.
6. A profile-only proof grants no library import, playlist write or playback
   control. Future accepted library/copy profiles request their own disclosed
   scopes and consent. HA's existing Spotify playback integration is separate.

There is no public App callback port, Cloudflare setup or helper running on the
browser computer in this workflow. `127.0.0.1` points to the browser computer;
it is not an alias for the HA App on a different host.

## Redirect alternatives and local access

My Home Assistant returns the browser to the instance selected for that browser;
it does not create a tunnel. Ensure that instance is reachable from that browser.
The private instance URL is not a Spotify registration value in the default
profile. The provider's code/state traverse the normal browser OAuth route;
do not copy or share the callback URL.

If My is disabled, the documented alternative is the exact existing
trusted HTTPS Core URI `https://<ha-host>/auth/external/callback`. Match the
base used to start setup. Its bridge compatibility remains unproven and gated
on live case L04; this preview does not enable it. No certificate-warning bypass or newly exposed App
port is permitted. Spotify's current redirect rules do not allow arbitrary
LAN HTTP addresses as registered callbacks; literal loopback is the exception.
Local HTTP/private-network return behavior is a compatibility test, not a
guarantee in this preview.

## Recovery decision table

| Message / condition | Intended action | What remains |
| --- | --- | --- |
| Pairing/fingerprint mismatch | Stop; confirm the actual App, then re-pair explicitly | No consent or provider grant created |
| Integration/App version incompatible | Install compatible reviewed releases | Existing verified App grants/history retained |
| New connection unavailable while HA is down | Restore HA/companion | Existing App grants may continue provider work and refresh |
| Consent denied or setup expired | Start a fresh native flow | No new connection; transient codes/verifiers discarded |
| Another administrator resumed setup | Return as initiating admin or start a fresh flow | Old active connection remains unchanged |
| Verification pending / acknowledgement lost | Query status; do not repeat completion | At most one exchange owner; unknown outcome stays explicit |
| Provider unavailable | Retry later according to bounded provider policy | No unnecessary reconnect demand |
| Grant invalid/expired | Use native **Reconnect Spotify** | Existing data/history retained; jobs needing access pause |
| Different account returned during reconnect | Cancel or create a separately identified connection | Existing connection is not silently relabeled |

## Backup, removal and disconnect

The App owns encrypted provider grants and is the only refresh owner. HA stores
safe pairing/connection references, not the grant. Its pairing key is a separate
private local file, readable by Core and host root; config entries are not
encrypted keystores. The selected automatic-start profile requires encrypted
HA backups. A decrypted Core backup may contain this native identity. Keep the
HA backup decryption key safe; the current destination setting does not certify
every historical or manual archive. The App needs no backup-inspection privilege.

After **Core restore or cloning**, first revoke the previous pair in the App and
then explicitly re-pair. The copied identity cannot reliably detect its own
cloning; restoring Core alone does not automatically revoke an old pair. If the
App is offline, new setup must wait for this operator procedure.

The App excludes all OAuth private keys from ordinary backups and encrypts its
provider grant records. After **App restore without those keys**, credentials
stay locked while non-secret library/history remains. The planned authenticated
admin action resets the local credential identity, fences previous attempts/
refresh/references and requires fresh pairing and provider consent. Startup must
not silently generate replacement keys. A missing key does not prove external
Spotify revocation. An encrypted recovery-kit export is not an enabled feature.
The [key contract](../architecture/local-key-custody-rfc.md) and
[bounded lab results](../development/local-key-custody-lab-2026-10-25.md) state
which mechanisms passed; full reset/rotation/restore conformance remains gated.

The [next recovery campaign](../development/oauth-recovery-and-pairing-lab-2026-10-25.md)
shows why an interrupted reset must remain pending: restarting or visiting
health cannot finish it. A future operator must explicitly resume through the
authenticated management surface, then pair and consent again. The file/SQL laboratory
uses stubbed admission; a separate guarded Core/Supervisor campaign now proves
native fresh-admin approval and actual Ingress Origin/CSRF reset/resume after
key loss. Neither is an available production admin recovery endpoint.
Dynamic CSR/certificate recovery is also research, not an installable helper.
A proposed recovery variant asks the initiating administrator for a fresh
native HA confirmation and returns a short-lived approval to the App's protected
form. The native actor/signature and App Ingress mechanisms have real-framework
HTTP proof. Browser UX, final packaging and pairing-permission disclosure still
need review; manually supplied lab cookies do not establish Chrome semantics.

**Unpair/remove auxiliary integration** disables new consent and pending bridge
authority. It does not mean an existing App grant was erased. If the App is
offline, cleanup is visibly pending until the operator revokes the pair there.

**Disconnect provider in Symphonia** stops new provider work, fences refresh and
completion, removes its local grant and runs provider-data cleanup. Provider-side
revocation is a separate result; if unsupported/unconfirmed, use Spotify Account
Apps to revoke the dedicated Symphonia grant. Never revoke the separate app
used by the user's native HA Spotify integration as a cleanup shortcut.

## Support evidence

Share only versions, negotiated profile, safe phase/result code and sanitized
correlation ID. Do not share callback URLs, codes/state, private instance or
Ingress routes, pairing challenges/keys, cookies, verifiers, client secrets or
tokens. Stable healthy connections do not generate periodic notifications.

The bounded native trial now has its own [install/retire runbook](native-oauth-trial.md)
and [dated validation report](../development/native-oauth-trial-acceptance-2026-10-30.md).
The report separates synthetic package evidence from the real owner trial;
neither establishes production companion readiness.
