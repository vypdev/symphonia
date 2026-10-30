# Native Spotify OAuth trial: setup and retirement

This is a proposed experimental validation package, not the production OAuth
companion. Use only the exact reviewed artifacts after their laboratory gates and
applicable installation approval. The [SDD](../../specs/native-oauth-validation-trial.md)
owns the finite contract; [preparation](../development/native-oauth-trial-preparation.md)
records the selected trust and source-delivery model.

## Prepare without starting the timer

1. Recheck Core2026.10.4, Supervisor2026.10.5, HAOS18.3, Frontend20260930.5
   and Green/aarch64. Unsupported Core stops visibly; never downgrade HA.
2. Review exact source revision, clean-tree status, installer/helper/App manifests,
   package hashes, required privileges, rollback and current test evidence.
3. Verify future Core backups are encrypted. This setting does not certify old
   archives; do not open/download any backup or decryption key for this test.
4. Use only a dedicated Spotify developer app and public Client ID. Register
   exactly `https://my.home-assistant.io/redirect/oauth`. No Client Secret or
   existing Spotify integration credential is used.
5. Add/install only the reviewed trial App source. Keep boot, watchdog and
   automatic updates off. Building/installing the App does not start its timer.
6. Upload the reviewed self-contained helper installer through existing File
   editor into an explicitly owned staging folder. In the existing Terminal,
   verify its SHA-256 against the reviewed receipt before running it. No new
   Python, SSH server, port or privilege is required.

The observed Terminal configuration root is `/homeassistant`; the installer
requires its `.HA_VERSION` marker and rejects symlinked/existing/unowned targets.
With the exact reviewed installer filename, run `sh <installer> install
/homeassistant`. It verifies every payload hash before publishing only the new
custom-component namespace. Perform HA's normal configuration check, then the
explicitly approved Core restart. Do not start the App until Core returns.

## Run one original twenty-minute trial

1. Manually start **Symphonia Native OAuth Trial**. Its original deadline is
   persisted immediately and cannot be reset by restart. Open admin Ingress.
2. In native **Settings → Devices & services → Add integration → Symphonia OAuth
   Trial**, enter the actual App slug, dedicated public Client ID and private
   bootstrap block. Acknowledge encrypted-Core-backup trust. Pair within five
   minutes. The block includes the installation, server SPKI and one-use challenge;
   never paste it into an issue or chat.
3. Open the entry's native **Reconfigure** and select **Connect Spotify**. Review
   official public-client maturity, exactly `user-read-private`, custody and
   deadline. Confirm, then complete Spotify consent through Core and My in the
   dedicated Chrome group. Never copy the callback URL, code or state.
4. Return to the native form. Callback receipt has only staged the return; it
   has not exchanged. Confirm anew as the initiating active administrator.
   The App exchanges once, verifies stable `account_id`, encrypts and commits.
5. When native status confirms App activation, restart **only the trial App**.
   Open native Reconfigure, choose **Verify refresh**, then explicitly confirm
   the one refresh. The same sealed grant and original deadline must reopen;
   App compares account identity and reports only the match outcome.
6. Record exact versions/package hashes, observed stages, restart, refresh/account
   result and limitations. Keep live acceptance separate from fake-provider and
   isolated-Core results. No personal hostname, actor/account identifier, token,
   cookie, grant, code, verifier or private key belongs in public evidence.

My returns the browser to its selected HA instance; it is not a tunnel. If that
selection is wrong, fix the normal My browser selection. Never expose an App
callback or bypass a browser certificate warning to make the test pass.

## Recovery decisions

| Observed state | Action | Retained facts |
|---|---|---|
| Pairing/pin failed | Retire and use a fresh explicit trial; preserve unknown files | No provider consent has begun |
| Denied/canceled/pending restart | Retire; no transient reconstruction | Safe references/deadline; no accepted grant |
| Callback staged | New initiating-admin native confirmation | Zero exchange before confirmation |
| Lost completion reply | Read native status; do not replay code | Durable App result or uncertain fence |
| Unknown exchange/refresh | Retire; no automatic retry | Outcome may exist remotely; safe uncertain marker |
| Invalid grant or unsupported identity/scope | Retire and start fresh only after correcting setup | No accepted expanded/guessed profile |
| Existing key missing/corrupt or App-only restore | Locked, never rekey automatically | Sealed evidence and original deadline |
| Original deadline elapsed | All local authority ends; stop/remove trial | External Spotify access may remain |
| Modified/unowned source or private file | Refuse forced cleanup; reconcile explicitly | Unexpected file is preserved |

## Retire and remove only the trial

1. Before expiry, use native **Reconfigure → Retire trial** and confirm as a
   current active administrator. The App revokes the pair and deletes the local
   sealed grant; Core removes only its hash-matching private files. A later
   refresh cannot reactivate them.
2. If retirement is unconfirmed, stop the App immediately and record uncertainty.
   Do not claim remote pair/grant deletion. If Core key cleanup is pending,
   preserve the files and follow their exact ownership/hash evidence; never use
   recursive wildcard deletion in `.storage` or `custom_components`.
3. Remove the native trial entry. Stop/uninstall only the distinct trial App and
   its disposable data. Do not touch normal Symphonia or Spotify.
4. Run the same exact helper installer with `remove /homeassistant`. It checks
   source hashes and its recorded runtime caches before deleting anything.
   Unknown/modified files stop removal. Check configuration and perform the
   approved Core restart after source removal.
5. Remove only the test repository registration/staging files created for this
   trial if no other App uses them. Retain a minimal sanitized evidence receipt.
6. Revoke the dedicated Spotify grant in Spotify Account Apps and separately
   record that outcome. Do not revoke the client used by native HA Spotify.

The timer limits the local App/channel, not Spotify's external grant. Local
deletion, backup key exclusion and encryption are not proof of remote revocation
or erasure of historical backups. Core restore/cloning requires revoking the old
App pair and explicit re-pairing; copied identity is not automatically detectable.
