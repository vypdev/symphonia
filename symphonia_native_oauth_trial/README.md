# Symphonia Native OAuth Trial

Experimental, manually started, twenty-minute validation App. It is separate from
the normal Symphonia/Spotify integrations. Package laboratory and owner acceptance
are recorded separately; a successful build is not OAuth acceptance.

```text
Install reviewed helper and App → native pairing → Spotify read consent
→ staged return → new same-admin confirmation → App-owned encrypted grant
→ restart only App → new refresh confirmation → compare account → retire
```

Only `user-read-private` is requested with a dedicated public PKCE Client ID and
exact `https://my.home-assistant.io/redirect/oauth`. No Client Secret, Cloudflare,
public App callback, playback, writes, library import or borrowed Spotify tokens.

Initial supported owner matrix: Core2026.10.4, Supervisor2026.10.5, HAOS18.3,
Frontend20260930.5, Green/aarch64 and the observed Chrome version. The helper
rejects another Core version; do not downgrade HA to run this trial.

Follow the [setup and retirement runbook](../docs/operations/native-oauth-trial.md)
and [preparation gates](../docs/development/native-oauth-trial-preparation.md).
Review the exact source/package hashes, permissions and Core restart before
installing experimental code. Automatic start and watchdog must remain off.

The App service runs as UID10001 after a narrow new-directory initialization.
It exposes no host ports, broad mounts or Core/Supervisor API credential. Admin
Ingress is read-only; every grant mutation uses a fresh native HA form. Native
pairing uses a five-minute one-use challenge, generated Core CSR and pinned TLS.
The callback alone never exchanges a code. This proves a new same-admin action,
not continuity with an original browser/login session.

Core's private pairing files require the trusted-host/encrypted-Core-backup model.
The App encrypts its grant using a separate local wrapping key. All App OAuth
private files under `/data/native_trial/oauth_keys` are excluded from backups.
Restore without those keys locks; no silent rekey, bootstrap or deadline extension.
Unknown exchange/refresh outcomes never replay automatically.

Use the native **Retire trial** action before removing the helper entry. Then
stop/remove only this App and hash-owned helper files. Modified or unknown files
are preserved. Local expiry/removal does not revoke Spotify access: revoke the
dedicated grant separately and record its actual outcome.

Contributor source artifacts are generated with
`python3 tools/stage_native_oauth_trial.py --output <fresh-owned-directory>`.
The helper script is self-contained, requires no host Python/network and refuses
existing or changed namespaces. App dependency and base-image identities are
pinned; the staged receipt identifies every source and package hash. See the
[test plan](../docs/development/native-oauth-trial-test-plan.md) for evidence limits.
