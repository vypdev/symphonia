# Code quality audit — 2026-10-04

This audit covers the owner-approved implementation foundation and the read-only operational dashboard at `82cbf87`. RepoWise and Graphify are diagnostic heuristics; their scores are not release gates or proof that a Draft capability is complete.

## Reproducible evidence

- `PYTHONPATH=src:. python3 -m unittest discover -s tests -q`: **293 tests passed**, with two socket-binding tests skipped by the local sandbox. The [GitHub Verify run](https://github.com/vypdev/symphonia/actions/runs/37232836791) passed Python 3.11–3.13, branch coverage, both UI builds and tests, architecture boundaries, SDD validation, whitespace, and lab configuration. Its combined line/branch report is **86%** overall; SQLite operation transitions are **84%**, the operation facade **92%**, runtime resources **91%**, and copy-target execution **84%**.
- `PYTHONPATH=. python3 tools/validate_specs.py` and `git diff --check HEAD~6..HEAD` passed. The SDDs and catalog still mark broader runtime, import, copy, and provider capabilities `Draft`; their blockers are unchanged.
- `PYTHONPATH=src:. python3 tools/storage_recovery_spike.py --operations 1000` proved backup validation, lease recovery after reopen, and cancellation quarantine on 1,000 synthetic operations.
- `repowise health . --format json`: average health **8.24/10**, hotspot health **5.71/10**. `repowise dead-code . --safe-only` found **0** safe dead-code candidates. RepoWise's historical coverage markers can lag the current GitHub coverage report; use the latter for current coverage.
- `graphify extract . --code-only --no-cluster` produced **2,435 nodes** and **5,175 edges**. `graphify god-nodes` reports `OperationRepository` degree **40** (48 before this audit) and `SpotifyAdapter` degree **25**. Node and edge totals are graph size, not quality scores. Architecture tests reject infrastructure imports from application modules.
- The rebuilt disposable Home Assistant App passed `python3 tools/ha_app_lab.py ingress-smoke`: App started, health, readiness, root, dashboard, and asset returned **200**; the dashboard was ready and an unauthenticated Ingress request returned **401**. The lab is bound to `127.0.0.1:7123`.

## Structural changes

| Area | Physical lines before → after | Current RepoWise score | Responsibility change |
| --- | ---: | ---: | --- |
| `sqlite_operations.py` | 1,413 → 283 | 3.85/10 | Lock-protected facade delegates complete claim, transition, and scheduling transactions; codec, schema, rules, and rollback are separate infrastructure modules. |
| `copy_execution.py` | 563 → 138 | 4.85/10 | Target and entry stages share a run context; target creation and recovery use one reconciliation path. The target module scores 9.7/10. |
| `runtime/resources.py` | 318 → 181 | 4.73/10 | Backup and partial-startup cleanup are isolated; failure-injection tests verify reverse close order and primary-error preservation. |
| `library_import_execution.py` | 218 → 125 | 4.05/10 | Persisted intent parsing and import-outcome policy are separate application modules; malformed retry counts fail before provider reads. |
| `providers/spotify.py` | 361 → 200 | 2.27/10 | Playlist traversal, entry/offset normalization, and HTTP/write error classification are separate provider modules behind the same adapter. |

The copy, import, cancellation, runtime-cleanup, and Spotify changes have deterministic offline regression tests. No application use case imports SQLite directly. Provider request and reconciliation ports remain explicit.

## Remaining quality and product risks

1. RepoWise still ranks `providers/spotify.py` lowest at **2.27/10**. Its remaining write methods have cyclomatic complexity up to 10, and history-based churn/defect signals materially lower the score. The SQLite facade is **3.85/10**, also affected by history and repeated delegation. These are measured follow-up targets, not a claim of current defects.
2. Combined CI coverage is **86%**. It is regression evidence, not exhaustive proof of every provider failure or Home Assistant lifecycle path. The local sandbox skips two socket tests; CI runs them, and the Ingress lab separately exercises live routing.
3. The UI currently provides the **read-only operational dashboard** with live diagnostics. Provider connection, library, playback, import, and copy feature views are not delivered by this foundation. Their SDDs remain Draft with unresolved product, provider, security, and platform gates; the quality work here does not remove those gates.
4. The disposable App smoke proves one local macOS/OrbStack profile. It does not establish a supported Home Assistant version/architecture matrix, full backup/restore/upgrade behavior, or provider-account integration.

Generated Vite JavaScript is a reproducible build artifact; source TypeScript checks, presentation-boundary checks, state tests, and asset reproducibility are the controls for the UI source.
