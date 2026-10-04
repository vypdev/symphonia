# Code quality audit — 2026-10-04

This audit covers the implemented foundation and read-only App dashboard at commit `fc880c6`. RepoWise and Graphify are diagnostic heuristics; passing checks does not mean every future feature is implemented or every design risk is closed.

## Evidence and commands

- `repowise health . --refactoring-targets --format json` and `repowise dead-code . --safe-only`: 0 safe dead-code findings. RepoWise still scores `sqlite_operations.py` and `copy_execution.py` at **1.14/10** because of their state-machine size and nesting; it scores `runtime/resources.py` at **2.68/10** for nested startup cleanup. Its `__main__.py` 0% coverage marker conflicts with the latest GitHub coverage report (**92%**), so that marker is stale.
- `graphify extract . --code-only --no-cluster` and `graphify god-nodes`: 1,605 nodes and 4,022 edges after the refactors. `OperationRepository` has **48** graph edges, down from **57** in the initial audit; application use cases have no direct SQLite imports. The global node and edge totals rose because modules and tests were added; they are not a quality score.
- `PYTHONPATH=src:. python3 -m unittest discover -s tests -q`: **278 tests**, 2 skipped locally because this sandbox disallows socket binding. The local Supervisor Ingress smoke separately checked live socket routing.
- `ui`: TypeScript check, production import/I/O boundary check, 5 state tests, and reproducible Vite build passed.
- [GitHub Verify](https://github.com/vypdev/symphonia/actions/runs/37229979554) passed Python 3.11–3.13, branch coverage, UI builds/tests/boundaries, specifications, whitespace, and lab configuration. Its coverage report: **83% overall**, **76%** for the SQLite operation adapter, **75%** for copy execution, **92%** for the CLI entrypoint.
- Disposable HA App rebuild and `ingress-smoke`: health/ready/root/dashboard/asset all returned 200; sessionless Ingress returned 401. In the real administrator browser, Refresh updated the timestamp and Diagnostics navigation rendered live state.

## Changes made from the initial audit

| Area | Before | After | Boundary gained |
| --- | ---: | ---: | --- |
| `sqlite_operations.py` | 1,413 lines | 1,194 lines | Diagnostic SQL and audit/timestamp codecs moved to focused modules; transactional state changes remain together. |
| `copy_execution.py` | 563 lines | 491 lines | Pure checkpoint validation moved to `copy_checkpoint.py`; processed entries now require a continuous prefix before provider writes. |
| `runtime/resources.py` | 318 lines | 169 lines | Atomic backup and schema preflight moved to `runtime/backup.py`. |
| `runtime/http.py` | 293 lines | 196 lines | Route selection and protected dashboard/static delivery moved to separate adapters. |
| `ui/src/main.ts` | 142 lines | 74 lines | Section rendering moved to `views.ts`; model and views are checked for browser I/O. |

The architecture tests scan every application module for infrastructure imports and the HTTP entrypoint for concrete adapter imports. A fake operation port test checks runtime substitution. Existing concurrency, crash/reopen, reconciliation, redaction, and Ingress tests protect the refactors.

## Remaining quality risks

1. `OperationRepository` remains a high-complexity adapter: RepoWise reports a 957-line class with 25 methods, including the transactional `checkpoint` state transition. A further split needs transaction and crash-recovery characterization so that moving code does not weaken lease atomicity.
2. Copy execution still has a six-level nested orchestration method. The next safe split is target create/reconcile and per-entry write/reconcile, with process-loss and unknown-outcome tests at each boundary.
3. `RuntimeResources.open` has nested partial-startup cleanup; Spotify request error mapping has a complex condition, and the library-import executor has prior defect history. These merit focused changes with their existing fixtures.
4. Coverage is useful regression evidence, not a completeness guarantee. The full runtime, provider authorization, playback, import, and copy SDDs remain Draft with product and platform blockers. Their current foundation code must not be presented as finished product behavior.

Generated Vite JavaScript is a reproducible build artifact; RepoWise's nesting warning on the minified bundle is not an actionable source-code target. The source TypeScript, boundary check, tests, and asset reproducibility check are the relevant controls.
