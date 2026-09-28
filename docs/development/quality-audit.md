# Local quality audit

**Snapshot:** 2026-09-27 on `develop`. This is a prioritization aid, not a release gate or a claim that a Draft SDD is implemented. The [development specification](development-specification.md) and [SDD catalog](../../specs/CATALOG.md) remain authoritative.

## Reproduce without provider access or an LLM

From the repository root, with the optional `repowise` and `graphify` CLIs installed:

```text
repowise health . --refactoring-targets
repowise dead-code . --safe-only
audit_dir="$(mktemp -d /tmp/symphonia-graph-audit.XXXXXX)"
graphify extract . --code-only --no-cluster --out "$audit_dir"
graphify god-nodes --top 20 --graph "$audit_dir/graphify-out/graph.json"
graphify affected OperationRepository --depth 1 --graph "$audit_dir/graphify-out/graph.json"
make verify
```

Use a fresh temporary output directory for each graph extraction. `--code-only` keeps Graphify's extraction local and skips LLM/document processing. RepoWise's `health` command also runs locally without an LLM. Neither tool is required by `make verify`; generated `.repowise/` and `graphify-out/` data are ignored by Git. Do not run LLM-backed generation, repository-history secret scans, or upload/export commands with private provider fixtures without a separate privacy review.

## Findings and interpretation

- RepoWise 0.45.0 reported `copy_execution.py` as a maintainability hotspot (score 1.65/10, maximum cyclomatic complexity 79), followed by `sqlite_operations.py` (score 1.65/10, 1,308 nonblank lines). These are heuristic scores, not failures by themselves. In particular, the copy executor coordinates uncertain external writes and must be refactored only with restart/reconciliation characterization tests.
- A bounded copy-executor change consolidated the repeated confirmation checkpoint and replaced list membership in the write loop with a synchronized set. RepoWise no longer reports its `membership_test_against_list_in_loop` marker; the maximum complexity remains 79, so the broader state-machine refactor is still open.
- Fault-injection characterization now covers process loss immediately after target creation and after an entry write, with a new worker lease; the entry case also closes and reopens file-backed SQLite stores. Both prove reconciliation precedes any repeat write. These tests protect a future state-machine extraction, but do not make the high-complexity executor itself simpler.
- Its reported line and branch coverage were `null`: the current test command runs deterministic `unittest` cases but produces no coverage report. Test count must not be presented as coverage. Add measured branch coverage before using a numeric coverage gate.
- After the transport extraction, Graphify's local AST graph contained 1,111 nodes and 2,872 edges. `OperationRepository` (56 edges) remained the most connected node. A change to operation persistence has a broad impact across the copy/import runners, runtime, and tests; inspect reverse dependencies before modifying its contract.
- Graphify makes the existing direct application-to-SQLite imports visible. The owner-approved foundation permits the current concrete composition, but an implementation-ready architecture should define repository ports and keep concrete stores at the composition boundary. This remains design debt, not a silently accepted dependency rule.
- The graph also exposed a YouTube Data adapter dependency on `spotify.py` for JSON transport. The transport now lives in `providers/http_json.py`, with an architecture guard against sibling-adapter imports and an offline test for correctly attributed, secret-safe failures.
- RepoWise marked `source_entries` as an unused export. It is a public convenience helper; static usage alone is insufficient evidence to remove a public API.

## Quality work in order

1. Preserve and expand fault-injection tests for unknown writes, cancellation, restart, and malformed checkpoints before reducing `copy_execution.py` complexity.
2. Define application repository ports and a composition rule in the relevant SDD/architecture documents before removing the current direct SQLite dependencies.
3. Measure line and branch coverage with an explicitly selected development tool, then target missing high-risk branches instead of a global percentage alone.
4. Keep architecture import tests and `make verify` as the dependency-free baseline; review graph/health deltas as advisory evidence rather than automatically deleting or rewriting code.

## Follow-up (2026-09-28)

Re-ran the documented offline commands against the local `develop` working tree while defining the listening broker. RepoWise still identifies `copy_execution.py` (1.6/10) and `sqlite_operations.py` (1.6/10) as XL hotspots; its safe-only dead-code pass found **zero** candidates. Its apparent highest refactoring ratio on `application/__init__.py` is an `untested_hotspot` heuristic, not proof of a defect or permission to remove a public export. No production refactor follows from a score alone.

Graphify's `--code-only --no-cluster` extraction produced **1,181 nodes and 3,060 edges**. `OperationRepository` remains the most connected symbol (57 edges); its one-hop dependents include runtime HTTP/resources, copy and import execution, the operation runner, and their tests. This reinforces the existing plan to define repository ports and preserve restart/reconciliation characterization before changing operation persistence. The broker design is kept out of domain/application imports and is not wired into this graph while its SDD is Draft.

The latest local `make verify` run passed **239 `unittest` cases (2 skipped)** plus specification/whitespace checks. Seven new validator cases exercise readiness blockers, implemented evidence, valid status transitions, malformed arrays, and missing SDD status. The isolated Lit spike also passed `npm ci --ignore-scripts`, TypeScript, presentation-boundary checks, three pure fallback tests, build, and relative-asset verification. Neither result proves Home Assistant integration, live playback, or visual parity. The new validator checks are structural guards, not substitutes for human review or live evidence.

The previously absent coverage measurement is now reproducible with pinned `coverage.py` 7.16.1 (development-only, not a runtime dependency):

```text
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[quality]'
make coverage COVERAGE_PYTHON=.venv/bin/python
```

The 2026-09-28 local Python 3.14 run measured **81% combined line/branch coverage** across 3,112 statements and 934 branch opportunities; it is not an 81% branch-only claim. Five new runtime HTTP contract tests brought `runtime/http.py` from 59% to 73%. Remaining examples are `apple_music.py` at 63%, `copy_execution.py` at 75%, `sqlite_operations.py` at 79%, and `__main__.py` at 0% under this unit suite. Those gaps guide targeted tests; no global minimum or release pass claim is inferred from a single number. CI now measures the same report on Python 3.13 as an additional non-threshold check. RepoWise's own coverage field may remain `null` until its ingestion is configured; do not present its heuristic scores as measured coverage.
