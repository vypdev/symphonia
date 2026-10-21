# Bugbot finding review — 2026-10-21

**Scope:** owner-requested corrections to the existing foundation and implemented dashboard.
**Baseline:** `0c466f975defafff1933fa2c4130baaa2dc20d1a`.
**Tracking:** [issue 9](https://github.com/vypdev/symphonia/issues/9), [original review](https://github.com/vypdev/symphonia/pull/1#pullrequestreview-5596763042).

The review confirms ten findings requiring corrections. Two describe deliberate
research/test boundaries rather than defects in the supported runtime. Their
documentation is clarified below. No unfinished capability becomes implemented
or ready. AGENTS.md and the installed Copilot assets remain unchanged; the
owner-authorized approval-policy adjustments are recorded below.

## Disposition and requirement traceability

| # | Finding | Disposition and change | Requirement / regression evidence |
| --- | --- | --- | --- |
| 1 | Copy journey offers exclusions | Valid. Remove the exclusion action; unresolved entries keep the plan blocked. | `SYM-PL-004`; [copy SDD](../../specs/one-time-playlist-copy.md), [planning tests](../../tests/test_copy_planning.py) |
| 2 | Best-effort plans bypass strict acceptance | Valid. Block non-strict or non-ready/non-write plans, including previously accepted plans at enqueue and both execution entrypoints. Keep historical values/digests readable. | `SYM-PL-004`, `SYM-PL-005`; [planning](../../tests/test_copy_planning.py), [legacy execution/admission](../../tests/test_copy_execution.py) |
| 3 | Stale probe reverses disconnect | Valid. The update atomically requires the observed secret reference and an active row; a losing probe reports conflict. Disconnect uses its dedicated cleanup path. | `SYM-ACC-004`, `SYM-SEC-004`; [independent-connection race](../../tests/test_sqlite_connections.py) |
| 4 | In-memory stores are separate databases | Not a defect in the declared foundation profile. Each adapter intentionally has an isolated ephemeral test store. File-backed runtime stores share one file; backup explicitly refuses `:memory:`. Clarify the runtime SDD. | [runtime tests](../../tests/test_runtime_resources.py): shared file schema, consistent backup and explicit in-memory refusal; [runtime SDD](../../specs/home-assistant-app-runtime-and-ingress.md) |
| 5 | HTTP callback spike discards the code | Not a production authorization regression. The loopback spike proves route/state isolation and secrecy; token exchange and an HTTP-to-exchange handoff do not exist and remain blocked by `RG-002`. Clarify that only the pure handler returns transient handoff data; the HTTP harness deliberately discards it. | `SYM-SEC-002`, `SYM-SEC-009`; [spike scope](oauth-callback-spike.md), [existing callback tests](../../tests/test_oauth_callback_spike.py) |
| 6 | Import ignores cancellation during read | Valid. Separate collection/publication and recheck cancellation and lease ownership before publication. Preserve the prior complete snapshot. | `SYM-JOB-004`, `SYM-LIB-004`; [complete/partial cancellation and lease takeover](../../tests/test_library_import_execution.py) |
| 7 | Late older import replaces current | Valid. Store the immutable observation, but atomically advance current only for a strictly newer UTC observation time. Equal times retain current. Return the actual retained current separately. | `SYM-LIB-004`, `SYM-ARCH-005`; [cross-connection/timestamp tests](../../tests/test_sqlite_library.py), [publication result](../../tests/test_library_import.py) |
| 8 | Apple videos classified as tracks | Valid. Map catalog/library songs to track, catalog/library music videos to video, and unrecognized resources to unknown. Preserve identity and order. | `SYM-PROV-006`, `SYM-PROV-018`; [mixed-page adapter test](../../tests/test_apple_music_adapter.py) |
| 9 | Migration wording forbids its local writes | Valid. Allow migration-controlled local writes while explicitly forbidding provider writes and keeping readiness blocked on interruption. | `SYM-HA-001`, `SYM-ARCH-003`; [runtime SDD](../../specs/home-assistant-app-runtime-and-ingress.md) |
| 10 | Catalog evidence escapes repository | Valid. Reject absolute, traversal and symlink escapes; do not read rejected SDDs or external Markdown files. | SDD standard repository-local evidence rule; [validator tests](../../tests/test_spec_validator.py) |
| 11 | Lab acts on matching label alone | Valid. Require both pinned image and lab label before status, Ingress smoke or stop accesses the named container. | `SYM-TEST-012`; [guarded lab tests](../../tests/test_ha_app_lab.py), [operator guide](ha-app-lab.md) |
| 12 | Dashboard read survives disconnect | Valid. Abort active/superseded requests and invalidate late completions; cleanup preserves the safe snapshot without inventing a read failure. | `SYM-UI-004`, `SYM-UI-009`; [client state tests](../../ui/src/model.test.ts), [dashboard SDD](../../specs/operational-dashboard.md) |

## Verification budget and acceptance

Minimum **27 distinct regression cases**: 3 copy-policy/admission, 2 connection
probe/cleanup, 6 import cancellation/lease/publication ordering, 5 Apple media
types, 4 catalog path boundaries, 4 lab command identities and 3 dashboard abort
and late-result cases. Parameterized cases count only for distinct inputs or
states. Existing runtime/callback tests verify the two scope dispositions.

Acceptance requires the complete offline Python suite, production and fixture
UI type/boundary checks, tests and builds, reproducible production assets,
specification/catalog/link validation, patch whitespace, and playback-lab
Compose configuration. Real local-socket tests must run without sandbox skips.
No live provider request or Home Assistant service startup is needed.

Local results on 2026-10-21: **310 Python tests passed without skips** on
Python 3.13, with **86% combined line/branch coverage** using coverage 7.16.1;
**10 production UI tests and 7 fixture UI tests passed** on Node 24. Both UI
type checks, presentation boundaries and builds passed, as did specification
validation, whitespace and the playback-lab Compose configuration check.

Copilot preservation is checked against the baseline for all 29 installed
assets and AGENTS.md, plus the managed pointer/profile/guide/skill hashes in the
unchanged setup manifest. Repository secrets, labels and runners are unchanged.
Only the approval-policy variable changes described below are authorized.
The maintainer explicitly authorized starting issue 9 with
`in-progress`; the Action created its exact managed branch from `develop`.

## Owner-authorized coverage and approval gate

The owner explicitly requested an **85% combined line/branch coverage minimum**,
CI producer attestation, and `guarded` approval mode. The minimum is enforced
by `coverage.py` through `pyproject.toml`, using the existing unmodified
`Verify` / `branch-coverage` job. The producer is GitHub Actions App **15368**;
the selected checks and all other policy values remain unchanged. After the
enforcing job succeeds on the current revision, `PR_APPROVAL_POLICY` changes
only `producerAttested` from `false` to `true` and `mode` from `recommend` to
`guarded`.

Acceptance requires the complete existing verification suite to pass, a
negative check proving the coverage command fails below 85%, current-revision
CI and Bugbot evidence, and a confirmed native approval before merge. The
coverage minimum is a regression floor, not evidence that unfinished product
capabilities meet their SDD acceptance budgets. No SDD status, provider
contract, runtime behavior, or architecture decision changes for this gate.

Local revalidation passed all **310 Python tests without skips**, **17 UI
tests**, both type/boundary/build pipelines, reproducible App assets, the
specification validator, whitespace, and Compose configuration. Coverage
remains **86%**. An isolated temporary 1% coverage measurement made the same
report command fail with exit status **2** and `fail-under=85`, confirming
that the configured floor is enforced. `npm ci` also reported existing
development-tool advisories for `vite` and `source-map-js`; their versions
and lockfiles are unchanged by this coverage/approval adjustment.

## Compatibility, recovery and architecture

Historical best-effort plans retain their IDs and digests but require a newly
reviewed strict plan before further writes. Older complete import observations
remain available as history; equal observation times retain the existing current
snapshot. No database schema or migration is added. The timestamp guard does not
implement the full import-session/version fencing still required by the Draft
import SDD. Cancellation remains cooperative at step boundaries; it does not
claim to roll back a publication that has already begun.

No new architectural decision is introduced: provider mapping remains in its
adapter, collection/publication coordination stays in application, atomic
updates remain in SQLite, and client cancellation stays within the existing
dashboard state/presentation boundary. ADR changes are not applicable. Product
scope, provider OAuth, secret storage and the other readiness gates remain open.

SDD manual checks retain every required concern, numeric budget, requirement
mapping, acceptance/failure/recovery/security boundary and catalog status. User
and operator guidance is updated alongside the tests and catalog evidence.
