# Install-local OAuth key custody laboratory

**Date:** 2026-10-25. **Status:** bounded non-production research; successor issue #28.

The owner selected automatic startup with an install-local protected key. This campaign proves App-style local-file mechanics, not a production vault or native HA pairing implementation. The owner subsequently selected the HA trust model with encrypted Core backups. App backup exclusions do not imply a Core integration exclusion.

## Executed environment

- Official Core 2026.10.3 image pinned to `ghcr.io/home-assistant/home-assistant@sha256:407b89cd11a8cb67d388d21739a226c74acbbebe1ac59e3b83b11b43ce76b98f`.
- Python 3.14.9 / cryptography 50.0.1; actual fixture UID 10001.
- Fresh labelled Docker volume, no network, read-only image and research source. The initial wrapper prepares only the new volume ownership and irreversibly drops groups/GID/UID before the campaign.
- A second container uses the same volume as UID 10001 with all capabilities dropped. No owner-HA config, Supervisor token, Spotify credential or public endpoint is mounted or called.

## Results

Twenty-two Boolean assertions pass: fresh initialization and read; refusal to reprovision an existing installation; plaintext grant absent from the sealed record; local wrapping key outside that record; key mode 0600; restore without keys locked; no replacement key generated during failed boot; wrong key, permissive file/directory, symlink file/directory, hardlinked key, short/oversized key, modified ciphertext, wrong authority profile and wrong installation rejected; recovery kit contains no plaintext local key; wrong recovery key rejected; explicit external-key recovery works; recovery key absent from ordinary local files.

The second container independently verifies the same local key and decrypted grant, without creating any new key. This is actual process/container replacement using the same labelled volume; it is not a Home Assistant restart or upgrade claim.

Twelve ordinary offline tests additionally cover private publication, no-replace initialization, permissions, symlinks, hardlinks, FIFO rejection without blocking, bounded reads, path/name rejection, failed replacement preserving the old record and foreign ownership. Those are filesystem-policy tests, not twelve production-vault acceptance cases.

## Recovery and threat boundary

AES-GCM uses a random 256-bit local key, random 96-bit nonce per encryption and installation/profile/version associated data. The generated local key is deliberately readable to the owning service UID, outside the database/encrypted record. Host root, other code in the same process/security identity and a live-memory compromise remain trusted/privileged threats. This does not provide hardware-backed or full-disk protection.

The restore fixture copies records and public metadata while omitting the key directory. Startup fails closed and never interprets encrypted state as a new installation. A distinct, explicit recovery action can restore the local key from an encrypted kit using a separately held random recovery key. The kit and recovery-key input UI, cross-store grant publication, rotation and full Supervisor restore remain unimplemented.

Supervisor App key-directory exclusion was independently measured in the earlier companion laboratory. This campaign models the excluded layout but does not repeat a native Supervisor archive or claim that a new App package was installed.

## Core backup finding and owner installation

Pinned Supervisor 2026.10.4 `supervisor/homeassistant/module.py` lines 62–75 and 451–496 use fixed Core exclusion patterns. No arbitrary custom-integration key exclusion is exposed there. Do not hide a private key under a misleading log/cache/archive filename or transiently remove it during backups.

On the owner's Chrome HTTPS session, the local backup destination explicitly showed encryption enabled. No key was displayed, no backup downloaded/created/restored, and no setting changed. This establishes the current local destination setting, not encryption of every historical or manually created archive.

## Remaining gates

ADR 0008 records the owner-selected Core identity/backup contract without claiming clone/restore detection from a copied identity. The final adapter must enforce that contract. Production key rotation/publication concurrency, recovery UX, package/library support, enrollment lifecycle and the actual bridge live matrix remain open. SDDs stay Draft until their complete gates pass; these research cases do not satisfy or replace the planned production budgets.

## Ordinary verification

The integrated research contribution passes **521 tests, no skips, 89% combined
coverage**, including twelve file-policy and six file/SQLite publication cases.
The latter explicitly fake AEAD; the separate container campaigns establish the
real encryption observations. These counts do not replace the 80/82/58 planned
production budgets or the 16-case bridge matrix. Specification validation and
all six manual catalog/link/requirement consistency checks pass.

Loopback HTTP cases require local socket permission. An earlier sandboxed run
could not bind those sockets; the same tests passed with loopback permission.
That environment limit was not treated as a code pass or ignored failure.

## Cleanup

After verifying the exact volume labels, owned marker and absence of consumers, the disposable volume and its five synthetic files were removed. It contained 20,480 allocated file bytes. Filesystem free-space change was not measured and is not inferred from allocated bytes. The pinned shared Core image is retained for reproduction. Source, tests and compact receipts remain for issue #28.

The owner About page separately reports Core 2026.10.3, Supervisor 2026.10.3, OS 18.3 and Frontend 20260930.5 (Home Assistant OS; system hardware label Home Assistant Green). The earlier Supervisor backup experiment used 2026.10.4; these distinct versions must not be presented as an owner-instance pass.

## Owner-selected Core profile: actual backup follow-up

The standalone guarded `core_key_backup_probe.py` ran in disposable Core 2026.9.4 with cryptography 48.0.1 (UID 0), through Supervisor 2026.10.4. It created a fresh synthetic EC pairing key in an owned 0700 directory and 0600 file, plus a private HA Store containing only a safe reference and public fingerprint. A separate process with no inherited Supervisor token reopened the same key and proved possession by signing and verifying a random message.

An actual unprotected Core archive contained the private identity, as expected for this profile. An actual protected archive recovered it with the correct password and rejected the wrong password. The selected reference member contained no private key. Core was never restored and no provider credential was used. Both generated backups and the exact Core fixture files were removed; a separate read confirmed zero owned backups remaining. The guarded lab was stopped again. These facts support the selected trust profile, not hardware protection, cloned-identity detection, the final integration package or a full restore on the owner instance.


## Official implementation evidence, checked 2026-10-25

These are dated primary implementation observations, separate from provider API
contracts; no community implementation is used as proof for key protection.

| Source | Observation and limit |
| --- | --- |
| [Supervisor 2026.10.4 Core archive implementation](https://github.com/home-assistant/supervisor/blob/2026.10.4/supervisor/homeassistant/module.py) | Fixed Core exclusion patterns, not an arbitrary custom-integration exclusion; native archive behavior independently exercised above. |
| [Supervisor 2026.10.3 Ingress authorization](https://github.com/home-assistant/supervisor/blob/2026.10.3/supervisor/api/ingress.py#L186-L195) | Backend rejects a missing/non-admin user for `panel_admin` Apps. This supports the planned admin-only reset boundary on the owner's observed Supervisor version; the final reset endpoint and non-admin browser case still need tests. |

## Reproduction and durable sources

The [local-key fixture](../../tools/ha_oauth_companion_lab/key_custody_probe.py),
[Core archive fixture](../../tools/ha_oauth_companion_lab/core_key_backup_probe.py)
and [12 offline cases](../../tests/test_ha_oauth_key_custody_fixture.py) are
non-production sources. The [lab recipe](../../tools/ha_oauth_companion_lab/README.md#install-local-key-and-core-backup-follow-up)
uses only an explicitly new labelled volume or the guarded disposable Core.
Do not run the archive probe on an owner/production Core. Its backup password
and key are random in-memory values and must not be printed or retained.

Requirements: `SYM-SEC-003`, `SYM-SEC-004`, `SYM-SEC-014` and `SYM-SEC-015` map
to record canaries, private file/reopen checks, distinct archives and locked
restoration; companion scenarios 11–13/L15 additionally require the final
reset/rotation/publication implementation. No full Core restore was executed.


## File/SQLite publication and generation-swap follow-up

The standalone [publication fixture](../../tools/ha_oauth_companion_lab/key_publication_probe.py)
ran in the same pinned Core 2026.10.3 image (Python 3.14.9, cryptography 50.0.1),
as UID 10001 with all capabilities dropped, a read-only source/image and no
network. Each case uses fresh synthetic file/SQLite state in an owned volume.

Eight child processes deliberately call `os._exit(83)`, bypassing Python and
SQLite cleanup: publication before record creation, after durable staging,
during an uncommitted SQL switch and after commit/before acknowledgement;
rotation after new-key staging, after record staging, after SQL switch and
after obsolete records retire. Reopening recovers the expected old/new grant,
retains history and removes unreferenced records/keys only under quiescence.
The SQLite state contains no plaintext grant sentinel. This is a single-record
synthetic generation swap, not full multi-account production rotation.

Four additional real-AEAD cases pass: stale publication after disconnect,
re-pair epoch change or competing completion is fenced; missing active key is
locked without provisioning. A subsequent guard additionally verifies, with
real AEAD and read-only state, that an explicit rotation also refuses missing
old keys before generating anything. Six ordinary tests use real files/SQLite
and explicitly fake AEAD to exercise two-connection races, stale/disconnect
fences, rollback, missing-key rotation and rejected tampered activation. Their
fake codec is not encryption evidence.

These are bounded P01–P07/P09/P10–P13 mechanisms and a partial P14 observation
from the key RFC fault plan. Partial writes during fsync, every missing/corrupt
old/new generation, live collector/owner leases, multi-connection rotation,
authenticated reset admission and P16–P18 remain open. No owner HA, provider
credential, public endpoint or production adapter was used.

The exact volume labels, twelve owned markers and absence of consumers were
verified before removal. Its 47 synthetic files occupied 294,912 allocated
bytes; the volume was removed. No filesystem free-space delta is inferred.
The first launch lacked the repository's `tools/__init__.py` anchor and failed
before creating fixture state; adding the unchanged package anchor fixed that
isolated runner setup. This was not an ignored data/crypto failure.


## Integration and scope

PR #27 is merged in `develop` at `25273eb3dcbf2eeb23585d6541744b8162b7a940`,
with the same tree as its tested head `fd64cd45d5ff0222a77ef778a4d8df33ea64d465`.
The research branch includes that base through the documented normal merge
recovery after the Action rejected this repository's different catalog schema;
[the recovery record](https://github.com/vypdev/symphonia/issues/28#issuecomment-6401331431)
retains exact refs, checks and the ownership reconciliation plan. No catalog
or protection was weakened to pass the foreign validator.

The exact publication campaign source was repeated after adding the missing-key
rotation guard; all eight process-death and four additional cases passed again.
This contribution records a key-custody direction and bounded mechanisms.
Full rotation, live collection, authenticated reset, final packaging/CSR and
actual browser/provider conformance remain open. It does not implement the
production capability or establish a pass on the owner's HA installation.
