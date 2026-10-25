# Install-local OAuth keys and backup trust profile

Status: proposed implementation contract; the owner explicitly selected automatic startup and the HA trust model with encrypted Core backups on 2026-10-25. No production implementation or readiness promotion.

## Purpose and trust boundary

The service can start without user input using an install-local key outside its ordinary database. The owning service UID and host root are trusted. Local key files are not a hardware keystore and do not protect against full host/process compromise. The setup copy must make that limit explicit. No key is an App option, command-line parameter, diagnostic field or ordinary UI response.

## Proposed App profile

Generate a 256-bit random installation key only during explicit first provisioning. Keep it in an owned 0700 key directory with 0600 regular, single-link files, checked owner and descriptor-relative no-follow I/O. This key directory is excluded by App metadata from Supervisor backups. There is no config/host mount, Core API token or access to another App's files.

Seal provider grant records using AES-256-GCM with a fresh random 96-bit nonce and version/installation/authority/secret-reference associated data. Only opaque references enter the product database. The crypto implementation and its pinned App/Python package still require compatibility and supply-chain evidence before production adoption.

Normal restart/upgrade reopens the existing key and records. Missing, malformed, permissive, linked, foreign or mismatched key state is blocked; startup never silently creates a replacement key over encrypted data. Database/history readiness must distinguish credential lock from corrupt general data.

The simplest initial restore policy preserves non-secret history and requires new provider consent when the excluded local key is missing. An explicit native-admin recovery action fences old attempts/jobs/grant references, creates a new installation key and requires fresh independent pairing and consent. It must not erase library/history or report that an old external Spotify grant was revoked. New key provisioning must not be reachable via health probes, startup or an unauthenticated route.

An encrypted recovery-kit mechanism has bounded research proof, but is not selected as a shipped export/import feature. A future kit needs a separately held recovery key, strict size/schema/domain/version bounds and authenticated recovery UX. Do not silently copy the installation key into the ordinary backup to make restores appear automatic.

## Owner-selected Core trust profile

Core owns only its OAuth pairing identity, never provider grants, codes or verifiers durably. Automatic startup can use a separately referenced private local file under HA's existing trusted-process boundary. Core backups may include that identity: unlike App metadata, the inspected Core backup implementation does not expose an arbitrary custom-integration exclusion.

The owner-selected automatic profile requires encrypted HA backups, truthful setup acknowledgement and operator handling as a full HA identity backup. It cannot certify the encryption of every historical/manual/Supervisor archive and must not claim that a decrypted HA archive contains no pairing material. The owner's current local destination encryption setting has been observed enabled, without displaying keys or altering settings.

A cloned/restored Core identity cannot be distinguished solely using an identifier copied in the same backup. Re-pair/revoke before admitting a restored instance must be an explicit operator lifecycle action unless an independent supported restore signal is proved. Do not advertise automatic clone detection or a guarantee of invalidating an offline copied private key. This refines the draft restore acceptance contract and requires corresponding SDD/global/ADR review before readiness.

Strict exclusion from all Core archives would require volatile Core keys with repeated pairing or a separate external facility; the owner did not select that profile. Never disguise a key as a cache/log/archive or patch Core's backup implementation.

## Rotation, publication and reset candidate — final conformance pending

This sequence defines the disposable fault campaign contract, not an implemented
transaction or an accepted production package. It refines `SYM-SEC-013`/`015`;
no two independent file/SQL writes are assumed atomic.

**Publication:** acquire the durable exchange owner before provider I/O and
snapshot connection/disconnect generation, pair epoch and key generation.
Encrypt a verified grant into a new immutable secret record before activating
its opaque reference. The record includes bounded schema/install/profile/key/
secret references in authenticated associated data. Use generated identifiers,
never provider names/IDs as filenames. Fsync the private record and containing
directory. A single SQLite compare-and-swap transaction may then activate its
reference only if that owner and every snapshotted generation still match.
After failed activation it is an orphan, never a connection. A lost acknowledgement
queries the durable result; an uncertain provider exchange is not repeated.

**Orphan collection:** initial research uses quiescent startup before admitting
any credential writer. Delete a record only after proving it is unreferenced
and no owner can later activate it. Runtime collection requires a durable
terminal owner/tombstone fence; age alone or a stale read is insufficient.
Disconnect increments the relevant generation and removes authority before
cleanup, so an old exchange/refresh cannot revive it. These rules preserve
non-secret history and make cleanup pending observable after interruption.

**Rotation:** keep immutable old/new key generations simultaneously. First
publish the new key privately; then stage newly encrypted records. Atomically
switch the active key generation and complete live reference set in SQL. Keep
the old generation until no active/staged record or admitted owner can require
it. Remove obsolete encrypted records before retiring their key. Interruption
before the SQL switch must leave the old generation usable; after it, the new
generation must reopen. A missing key or mismatched record must lock access,
not fall back or create a replacement. The final multi-connection lock/lease
and exact transaction schema remain to be measured.

**Explicit reset after lost App keys:** retain a healthy authenticated Ingress
recovery surface independently of the internal pairing/TLS listener. Validate
a fresh native administrator, exact trusted Ingress, Origin and CSRF. Record a
durable reset intent and increment the credential generation before any new
key; invalidate old attempts, pairs, refresh owners and secret references.
Preserve ordinary library/history. Publish a new private installation identity
only for that authorized action, then require fresh pairing and consent. On
crash, remain `reset_pending`/locked and require explicit admin resume; startup
and health probes cannot silently finish by generating a new identity. A reset
never claims to revoke an external grant whose credentials are unavailable.

### Fault campaign plan (18 distinct cases; bounded follow-up results below)

| Cases | Interruption/attack | Required observation |
| --- | --- | --- |
| P01–P04 | Before record fsync, after fsync/before SQL, during uncommitted SQL, after commit/before acknowledgement | Old or committed new reference, never a dangling active grant; lost acknowledgement uses status |
| P05–P07 | Disconnect, re-pair or competing completion between staging and activation | Stale compare-and-swap rejected; no revived grant; obsolete record collectible |
| P08–P09 | Collector versus staged owner; restart with unreferenced sealed record | No deletion of an activatable/live record; quiescent orphan removed safely |
| P10–P13 | New key staged, new records staged, SQL generation switched, obsolete records retired | Reopen uses the correct old/new generation; referenced key never removed |
| P14–P15 | Missing old/new key or corrupted rotation record | Locked state and preserved non-secret history; no automatic rekey |
| P16–P18 | Reset after durable fence, after new key/before publication, and unauthorized reset/health request | Locked `reset_pending` until explicit admin resume; old owners remain fenced; unauthorized request changes nothing |

Use real process death/reopen for the file/SQL points and real authenticated
adapter requests for reset admission. The 18-case research plan does not add
to or replace the unchanged production budgets. Results must identify the
exact crypto/runtime/package and distinguish synthetic state from owner HA.

## Planned acceptance before production

### Fresh reset authority candidate — not accepted or implemented

The inspected Supervisor 2026.10.3 ingress implementation caches resolved user
records. `panel_admin` and a trusted user header therefore do not alone prove
that an existing session's actor is still active/admin at reset time. See
[API lookup/cache](https://github.com/home-assistant/supervisor/blob/2026.10.3/supervisor/api/ingress.py#L359-L395)
and [cache lifetime](https://github.com/home-assistant/supervisor/blob/2026.10.3/supervisor/ingress.py#L37-L40).
This is dated implementation evidence, not a new HA guarantee.

Candidate recovery requires two bound surfaces. Admin-only App Ingress creates
a short-lived non-secret request identifier bound to its browser/CSRF context,
App installation, current pair/epoch and exact reset-or-resume purpose. A native
companion flow validates a fresh current administrator at begin and confirmation,
matching that actor to the request. Its existing protected Core key signs the
bounded request/actor/purpose/deadline. The explicit native setup view may show
this short-lived approval document for return to the App; it contains no private
key/provider credential and never enters URLs, logs or config entries.

Final admission stays in trusted Ingress, with exact Origin, browser/CSRF,
actor, request/pair/epoch/purpose, signature, expiry and consume-once checks.
The App verifies against its retained public pairing identity; missing App
private keys do not permit a plaintext management fallback or a new listener.
Only then does the durable reset fence precede new key publication. An expired
or interrupted approval needs a new native confirmation; startup/health cannot
approve or resume. A copied or missing Core identity needs the separately
reviewed operator recovery procedure; no anonymous fallback is proposed.

This extends recovery UX and the disclosed pairing authority and needs security,
HA-platform and UX review before acceptance/readiness. A native HTTP/signature
prototype can test fresh identity separately from real Supervisor/Ingress and
browser admission; stubs must be named and cannot close the complete gate.

### Planned checks

1. Explicit provisioning only; automatic restart reads the same key and grant.
2. Wrong key/owner/mode/type/link/profile/install/version/size cannot unlock state.
3. Actual Supervisor backups contain encrypted App grants and no App local key.
4. App-only restore without key blocks credentials and preserves non-secret history; reconsent creates new identity after fencing previous refs.
5. Core key file/entry/backup rules match the owner-selected profile and disclose all limits.
6. Key rotation and staged-secret publication survive interruption at every file/SQL fence; disconnect cannot be reversed by a stale owner.
7. Logs, diagnostics, App options, API/UI and ordinary exports contain no provider grant or usable App key canaries.
8. Supported App package and exact owner-HA versions pass; no broad mounts, Core credentials or authority escalation.

These are research/design gates. The separate companion 80-case, authorization 82-case, runtime 58-case budgets and 16 live bridge cases remain unchanged until their implementation contracts are ready.


## Publication fault follow-up result

The [dated follow-up](../development/local-key-custody-lab-2026-10-25.md#filesqlite-publication-and-generation-swap-follow-up)
records eight actual process deaths and four additional real-AEAD fence/key
cases, plus six ordinary file/SQL policy tests with fake AEAD. It establishes
single-record generation-switch mechanics and quiescent orphan handling,
not every planned fault point, full production key rotation, live writer
collection, reset admission or the final adapter/package. The remaining gates
above are retained; none of these counts replaces a production test budget.

The [successor campaign](../development/oauth-recovery-and-pairing-lab-2026-10-25.md)
adds eighteen actual process deaths across three-record publication/rotation and
durable reset ordering, four real missing/wrong-key cases and twenty-three
ordinary file/SQL policy cases with fake AEAD. This includes buffered private
writes and durable two-link publication; no simulated power-loss claim is made.
Admitted writers pin staged files; a complete SQL reference set switches at once.
Interrupted reset remains pending until fresh explicit resume and preserves history.
The isolated reset Boolean remains a stub. Separately, thirty-three actual
Core 2026.9.4/Supervisor 2026.10.4 wire observations establish CSR/renewal,
locked-key Ingress survival, native fresh-admin approval and App Origin/CSRF
redemption with interrupted reset/resume. Ingress returned 200 after user
deactivation, while native confirmation returned 401: cached headers are not
fresh authority. Browser cookies were manually supplied over lab HTTP, not
validated by Chrome. Thirteen ordinary boundary/operator/renewal guards supplement that
experiment. Full live lease/reader/reset/collector concurrency, final packaging/
backup/restore, proposed recovery authority/UX review and native browser/provider
conformance remain gates. The accepted custody direction and Draft status remain.

A separate actual child death immediately after credential reset commit and
before issuer revocation now passes nine observations. The durable completed
reset phase fences the old pair on startup before TLS; reconciliation is
idempotent and never rekeys/rearms enrollment. Reset and renewal share an
authority lock; the TLS worker reads through its own read-only SQLite connection.
This research fixture ends unpaired and explicitly requires a fresh disposable
namespace. It does not implement production post-reset enrollment UX.
