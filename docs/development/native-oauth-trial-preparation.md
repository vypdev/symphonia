# Native OAuth trial preparation and contract review

Reviewed 2026-10-30 against the [owning SDD](../../specs/native-oauth-validation-trial.md)
and all questions in section 8 of the [standard](../../specs/README.md).
This is an engineering contract review under the owner's standing authorization,
not a claim that the owner reviewed final screenshots or installed software.

## Readiness decisions

| Review concern | Resolved contract and evidence |
|---|---|
| Current behavior | No installed trial; dated research is bounded. Actual owner version preflight and Core source/runtime identities are recorded in the hook report. |
| Understandable journey | Native pair, disclosed read consent, stage, fresh same-admin confirmation, App-owned exchange, restart, confirmed refresh, account comparison and retirement. |
| Defaults and invariants | Dedicated opaque public Client ID, exact My redirect, user-read-private, named App target, fixed port, five-minute bootstrap and original twenty-minute deadline. No secret input, arbitrary endpoint or privilege override. |
| Architecture | Inward pure/application ports; framework and provider adapters; App-only encrypted grant. Real native flow probe verifies the callback-to-confirmation API pattern without default Core token paths. |
| Proportional tests | 54 distinct planned cases, allocations 12/12/12/10/8 with reciprocal requirement mappings. Existing research contributes zero final-package cases. |
| Documentation and migration | Named source manifests, runbook, test plan, hook/preparation/acceptance reports and scoped rollback. No production/native Spotify data import or migration. |
| UI states | Native forms are the mutation surface. The finite read-only bootstrap/status page is an explicitly accepted temporary engineering surface, using semantic HTML, HA typography and common state vocabulary. It creates no new design system or private frontend dependency. |
| Action clarity | Pending, confirm, partial, locked/uncertain and complete examples state observed facts, retained state and one next action. Complete OAuth verification still requires explicit retirement. |
| Security and recovery | Fresh active-admin checks; pinned CSR/TLS; no broad API or mounts; durable consume-once admission; atomic sealed publication; missing-key lock; protected files and encrypted-Core/excluded-App backup model from ADR0008. |
| Normative verification | Section14 names all distinct observable cases; section16 acceptance and section17 reciprocal links agree. Actual TLS, package, restart, backup and owner-browser assertions remain future gates, not satisfied by structure. |
| Decisions and owner authority | Native My route and automatic protected keys/encrypted Core backups were explicitly selected by the owner. The owner authorized implementation/testing after applicable readiness and continuation of issue32. Exact-package and browser action-time installation approval still apply. |

The bounded contract is **Ready for implementation**. This decision does not mark
any package case or live acceptance complete. Broad companion, authorization,
runtime and UI-foundation readiness remains unchanged. The temporary read-only
status exception applies only to this disposable trial.

## Existing owner tools and delivery

Read-only Chrome preflight observed Core2026.10.4, Supervisor2026.10.5,
HAOS18.3 and Frontend20260930.5. Existing Terminal has sh, tar, sha256sum,
base64, mv and mkdir; python3 is absent. Its real Core configuration mount is
/homeassistant. No software, configuration, backup or provider consent changed.

The helper delivery will be a reviewed self-contained POSIX-shell payload with
an exact SHA-256 manifest, using the existing tools. It must scope publication to
the named custom-component namespace, reject links, conflicts and unowned files,
verify before atomic publication and preserve modified/unrelated rollback
sentinels. No Terminal permission expansion or extra host Python is required.
Core supplies Python for the installed helper itself. The App has a distinct
slug and no host port, Core/Supervisor API or broad mounts.

## Gates before owner installation

1. Complete ordinary tests and the eight exact-package laboratory cases.
2. Verify exact source/package hashes, manifests, least privileges and removal.
3. Review actual native forms and read-only status, keyboard, narrow viewport,
   English/Spanish and safe outputs. No screenshot approval is claimed yet.
4. Recheck the owner versions, encrypted-Core-backup setting and runtime tools.
5. Present exact experimental packages and restart consequence for applicable
   browser action-time approval. Then install only the reviewed artifacts.
6. Register the exact My URI for the dedicated Spotify developer app, then
   observe native pairing/consent/confirmation, App restart, confirmed refresh
   and local account match in the dedicated Chrome test group.
7. Retire/remove only owned artifacts and separately observe provider revocation.

Final package hashes and runnable owner installer commands are intentionally
absent until those artifacts exist and pass their laboratory gates. No token,
code, verifier, key, private hostname or session route belongs in public evidence.
