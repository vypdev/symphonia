# ADR 0008: Install-local OAuth keys and distinct HA/App backups

- Status: Accepted key-custody direction; implementation and recovery conformance remain gated
- Date: 2026-10-25
- Deciders: repository owner, explicit automatic-start and encrypted-HA-backup choices
- Scope: native OAuth companion pairing identity and App-owned provider credential keys
- Related: [ADR 0007](0007-home-assistant-oauth-companion.md), [key contract](../architecture/local-key-custody-rfc.md), [bounded evidence](../development/local-key-custody-lab-2026-10-25.md)

## Context

The owner selected automatic startup with a protected installation-local key,
then explicitly chose the HA trust model with encrypted Core backups after the
different exclusion mechanisms were explained. Private HA Store files are not
encrypted merely because they have mode 0600. Supervisor App backup exclusions
work; no arbitrary per-integration Core key exclusion was established.

The earlier proposed sealed-Core-key record is superseded by this explicit
trusted-host profile. No hardware/external key service or manual unlock after
ordinary restarts is required. This refines key custody, not ADR 0007's authority:
Core still owns no durable provider code, verifier, grant or refresh session.

## Decision

1. Trust the host and owning service identity. Installation-local keys permit
   automatic restart. They do not protect against host root, other privileged
   code in that identity, a full live-filesystem copy or live-memory compromise.
   Setup must disclose this boundary rather than describe it as hardware sealing.
2. Keep the Core OAuth pairing private key in a separate owned directory with
   mode 0700 and regular single-link mode-0600 files. A config entry contains
   only an opaque key reference and safe public pairing/configuration metadata.
   No private key enters the config-entry payload, log, diagnostic or UI DTO.
3. Core backups may contain that native pairing identity. Require encrypted HA
   backups and treat their decryption key as protecting a full HA identity.
   A decrypted protected Core archive is allowed to contain the pairing key.
   This does not certify every historical/manual archive or add backup-inspection
   privileges to the App. Never disguise keys as excluded cache/log/archive files.
4. Encrypt provider grants only in the App using a separately owned install-local
   key outside the ordinary database/export. Exclude all App OAuth private-key
   material from ordinary Supervisor App backups. A candidate implementation uses
   AES-256-GCM and installation/profile/version/reference associated data; the
   final record, library, packaging and publication contracts still need proof.
5. A restart reads existing valid keys. Missing, malformed, mismatched, permissive
   or replaced key state locks credential operations. Startup must never silently
   generate a replacement key over encrypted state or clear general user data.
6. App restore without excluded keys needs explicit authenticated recovery and
   fresh consent, preserving non-secret library/history and fencing previous
   attempts, refresh and credential references. The precise reset/publication
   transaction and recovery UI remain implementation-readiness gates. An encrypted
   recovery kit is research evidence, not a selected shipped export/import feature.
7. A copied Core identity cannot self-detect cloning from identifiers in that same
   copy. The restore procedure requires the operator to revoke the old App pair
   and explicitly re-pair before new consent. Do not claim automatic invalidation
   of an offline copied private key. App pair revocation and provider disconnect
   remain separate operations with honest external-revocation outcomes.
8. OAuth and playback credentials stay independent. No key/backup operation grants
   playback, generic Core/API, filesystem or provider-proxy authority.

## Evidence and limits

The local-key fixture passes 22 bounded crypto/filesystem assertions and a second
container reopens the same key/grant as UID 10001. Twelve ordinary file-policy
tests cover permission, owner, link, type, size and publication failures.

An actual disposable Core 2026.9.4 / Supervisor 2026.10.4 experiment stores a
synthetic EC key in a private file and only a safe reference/public fingerprint
in HA Store. A new process proves possession; an unprotected native archive
contains the identity, a protected archive recovers it with the right password
and rejects the wrong password. The exact fixture files and both backups were
removed. Core was never restored. The owner's current local backup destination
was separately observed encrypted; its configuration was not changed.

These mechanisms do not prove the final integration, CSR/certificate lifecycle,
rotation/reset/publication races, complete supported matrix or a real Spotify
bridge. The companion, authorization and runtime SDDs remain Draft until their
remaining gates are resolved. The owner authorized continuing through those
gates and implementation/testing; that authorization does not itself make an
SDD ready or establish release conformance.

The [successor recovery/CSR research](../development/oauth-recovery-and-pairing-lab-2026-10-25.md)
adds eighteen three-record reset/rotation/publication process deaths, four real
missing/wrong-key cases, three CSR-issuance deaths and twenty-eight real native
HTTP/signature observations. Separately, thirty-two actual Core/Supervisor wire
observations establish CSR enrollment/renewal and native signed reset/resume
through App Ingress after key loss. This narrows mechanism uncertainty; the
short-lived recovery approval's pairing-authority/UX disclosure still needs
review. Manual HTTP cookies do not establish browser semantics. No new recovery
permission is accepted by this evidence, and the custody direction is unchanged.
Final adapter/package, concurrency, restore and live provider/browser conformance
remain open.

## Alternatives and consequences

- Manual unlock after restart keeps the wrapping key off disk but was not the
  owner's preferred operating model.
- Volatile Core pairing keys avoid persistent identity in Core archives but
  require pairing after each Core restart; the owner did not select this.
- External/hardware key custody can provide stronger host separation but adds
  infrastructure and is outside this initial profile.
- Backing up App keys beside encrypted grants makes restore simpler but defeats
  the selected App export boundary. It is rejected for ordinary App backups.
- Encrypted HA archives deliberately retain native HA identity. Operators must
  keep the backup key safe and follow revoke/re-pair on restore. No stronger
  clone-detection or per-integration host sandbox is promised.

## Verification before implementation/release

Reconcile `SYM-SEC-003`/`014`/`015`, all three SDDs,
catalog, RFC and recovery guide. Keep the 80/82/58 production budgets and the
16-case bridge matrix distinct from research assertions. The final App must
prove actual key exclusions, fail-closed startup/reset, publication/refresh/
disconnect fencing, log/export canaries and target-version install/restart
behavior before its corresponding conformance claims are accepted.
