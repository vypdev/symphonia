# Native OAuth companion design review

**Date:** 2026-10-25. **Work:** [issue #26](https://github.com/vypdev/symphonia/issues/26),
[draft PR #27](https://github.com/vypdev/symphonia/pull/27).
**Scope:** owner-requested design/specification only; no implementation,
installation, owner-HA modification or new live OAuth run.

## Review outcome

[ADR 0007](../decisions/0007-home-assistant-oauth-companion.md) records the
owner's native auxiliary-integration direction and explicitly supersedes the
OAuth clauses in the previous App/playback ADRs without rewriting them. The
[new SDD](../../specs/home-assistant-oauth-companion.md),
[RFC](../architecture/home-assistant-oauth-companion-rfc.md) and
[operator preview](../operations/home-assistant-oauth.md) make the proposal
reviewable. Authorization/runtime SDDs, global requirements, source evidence,
open gates and both catalog views agree on that direction.

| Manual SDD check | Result / limit |
| --- | --- |
| User outcome, flows, states and recovery | Native pairing/connect/reconnect/confirmation, denial, unknown outcome, removal and disconnect described |
| Ownership and trust | Core stages; App exchanges/stores/refreshes; independent OAuth pair; fresh actor proof remains a gate |
| Observable contract changes | Native-flow/current-admin authority replaces the trial's original App cookie requirement explicitly; no exact-browser/login-revocation claim |
| Numeric budget | 12 + 20 + 18 + 10 + 20 = **80 planned offline cases**; **16 live cases**; existing 82/58 budgets preserved |
| Traceability | New `SYM-HA-012` and `SYM-SEC-012`–`014` defined in global architecture and mapped to acceptance/matrix |
| Configuration/compatibility | Proposed fixed bounds, one pair entry, main reconfigure/reauth flow, internal transport and no fallback documented |
| Secrets/backup/restore | App-only grants, protected pair key references, abandoned transient attempts and staged-secret recovery; key sources/backup proof still blocked |
| UI and docs | Native HA forms intentionally host-owned; App status inherits UI foundation; setup/recovery preview linked |
| Non-applicable concerns | Audio/player control, import/write policy, unofficial providers and standalone explicitly outside this vertical |
| Current facts vs proposals | Dated official evidence separate from moving-branch community evidence and unproven protocol |
| Readiness and approval | New companion and existing authorization/runtime remain **Draft**; design direction is not permission to implement |

## Validation performed

- Repository specification validator passed, including catalog/status, requirement
  references and owned Markdown path links.
- Existing validator regression suite: **20 tests passed**.
- Whitespace check passed. The change contains documentation/specification only;
  no production, research-App, dependency, workflow or protection changes.
- A local structural audit confirmed all 20 template sections, summed budget,
  16 named live cases, global requirement definitions and Draft/catalog blockers.

No 80-case implementation suite or live companion pass is claimed. The earlier
466-test research implementation result belongs to its earlier source revision;
it is not a conformance result for this new design. Native extension/actor hooks,
private pairing, keys/backup, App activation recovery and supported-version
evidence must pass `RG-008` before implementation readiness can be considered.
