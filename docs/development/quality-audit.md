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

After the SDD-validator increment, a fresh Graphify code-only extraction produced **1,197 nodes and 3,103 edges**; `OperationRepository` remained first at 57 edges. RepoWise safe dead-code analysis still reported **0 findings**. These are architecture/navigation snapshots, not a claim that the high-coupling persistence or copy hotspots are fixed. No production broker code was introduced while the listening SDD remains Draft.

The latest local `make verify` run passed **239 `unittest` cases (2 skipped)** plus specification/whitespace checks. Seven new validator cases exercise readiness blockers, implemented evidence, valid status transitions, malformed arrays, and missing SDD status. The isolated Lit spike also passed `npm ci --ignore-scripts`, TypeScript, presentation-boundary checks, three pure fallback tests, build, and relative-asset verification. Neither result proves Home Assistant integration, live playback, or visual parity. The new validator checks are structural guards, not substitutes for human review or live evidence.

The previously absent coverage measurement is now reproducible with pinned `coverage.py` 7.16.1 (development-only, not a runtime dependency):

```text
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[quality]'
make coverage COVERAGE_PYTHON=.venv/bin/python
```

The 2026-09-28 local Python 3.14 run measured **81% combined line/branch coverage** across 3,112 statements and 934 branch opportunities; it is not an 81% branch-only claim. Five new runtime HTTP contract tests brought `runtime/http.py` from 59% to 73%. Remaining examples are `apple_music.py` at 63%, `copy_execution.py` at 75%, `sqlite_operations.py` at 79%, and `__main__.py` at 0% under this unit suite. Those gaps guide targeted tests; no global minimum or release pass claim is inferred from a single number. CI now measures the same report on Python 3.13 as an additional non-threshold check. RepoWise's own coverage field may remain `null` until its ingestion is configured; do not present its heuristic scores as measured coverage.

## Follow-up (2026-09-30)

Prepared a disposable Home Assistant Supervisor/App/Ingress test lane using the
maintained official [Apps devcontainer](https://developers.home-assistant.io/docs/apps/testing/).
The repo's App manifest is nested under `addon/`, so a small staging tool now
builds a local-only App source directory from that manifest, the root Dockerfile,
and `src/`; it removes the published image reference only from staged metadata.
Nine tests cover staging, cleanup of previously staged files, interrupted-stage
recovery, path/symlink rejection, VS Code tasks, and the devcontainer profile.
The runtime has not been launched here: the configured macOS Docker socket is
not accessible to this session. Compose configuration validation does pass
without starting containers. No playback broker or provider behavior was
implemented; the listening and App-runtime SDDs remain `Draft`.

The current offline suite passes **248 tests (2 skipped)**. `coverage.py` 7.16.1
measures **81% combined line/branch coverage** (3,112 statements and 934 branch
opportunities). RepoWise ingested Cobertura for the same run and reports 84.3%
line coverage and 69.5% branch coverage; it has no per-test map because the
suite does not emit test contexts. The percentages use different denominators
and should not be compared as if they were one metric.

RepoWise's offline index contains 147 files, 1,119 nodes, and 2,586 edges. Its
safe dead-code check reports zero cleanup candidates. The main persistent
hotspots remain `copy_execution.py` and `sqlite_operations.py`; the new staging
tool's initial complexity/nesting findings were split into small helpers. Its
remaining filesystem-in-loop signals correspond to reading/writing each staged
file, which is intrinsic to this copy operation rather than a repeated query.
No code was removed based on heuristic findings.

A fresh local Graphify extraction reports **1,917 nodes and 4,087 edges**.
`OperationRepository` remains the largest hub (57 edges), so its existing
concurrency/recovery test gates remain important. Graphify traces
`stage_application()` directly to its characterization tests; the app staging
work stays outside domain/application modules. These graphs are navigation and
impact evidence, not a claim that a live HA runtime has passed.

## Follow-up (2026-10-01)

The first inward-port increment moved authorization-attempt and provider-connection
repository contracts into `symphonia.application.ports`. Both use cases now
import those protocols; an AST test guards the boundary. Other application
services still import concrete repositories and remain design debt. RepoWise
reported no safe dead-code candidates. A fresh code-only Graphify extraction
contained 1,229 nodes and 3,180 edges before the port change, with
`OperationRepository` still the largest hub at 57 edges. After both increments,
the graph has 1,253 nodes and 3,234 edges. `AuthorizationService` now refers
to `AuthorizationAttemptPort`; `OperationRepository` remains the largest hub.
RepoWise's remaining coverage-gradient signal for the CLI uses its existing
coverage index and is not a measurement of the new tests. No provider
capability was promoted out of Draft.

CLI lifecycle characterization covers graceful stop, failed server creation,
listener-close failure, and invalid configuration. The ordinary offline suite
passes 253 tests (2 skipped) on Python 3.14 and 3.13. Specification validation,
the isolated Lit spike checks/build, and disposable playback-lab Compose
configuration also pass locally. GitHub checks still require an authorized
push and remote observation.

## Follow-up (2026-10-02)

The playlist-import foundation now takes a projection repository port and
returns a domain-owned published snapshot value. The SQLite adapter keeps its
previous exported name as an alias. A fake-port test confirms that partial
observations do not call publication, while the SQLite test checks the
compatibility alias and the architecture test rejects an infrastructure import
from the use case. The Draft import SDD still blocks production import work.

RepoWise found no safe dead-code candidates. A fresh code-only Graphify graph
contains 1,260 nodes and 3,260 edges; `LibraryImportService` uses
`PlaylistProjectionPort`, and `OperationRepository` remains the largest hub at
57 edges. The offline suite passes 254 tests (2 skipped) on Python 3.13 and
3.14, including specification validation.

The copy-plan foundation now takes an application-owned plan repository port
and uses a domain-owned accepted-plan record. Existing SQLite imports remain
available through an alias. The architecture test protects the copy use cases
against a direct plan-adapter import; it does not yet prohibit their operation
repository dependency. RepoWise again reports zero safe dead-code candidates.
Graphify shows both copy use cases depending on `CopyPlanPort`; its current
code-only graph has 1,268 nodes and 3,289 edges, with `OperationRepository`
still first at 57 edges. The offline suite passes 255 tests (2 skipped) on
Python 3.13 and 3.14. The Draft copy SDD's acceptance and provider-write gates
remain open.

The 2026-10-02 isolated UI review added seven synthetic Lit views and pure
fixture-state tests, with no App integration. RepoWise's offline health report
still places `copy_execution.py` and `sqlite_operations.py` among the main
maintenance hotspots; its safe dead-code pass found **0 candidates**. A fresh
Graphify code-only graph contains **1,300 nodes and 3,409 edges**, with
`OperationRepository` still first at 57 edges. `graphify affected SymUiSpike`
reported no affected nodes, so this extraction is not evidence that all UI
dependencies are represented; the fixture's own import/boundary check remains
the direct guard. The local Python suite passes 255 tests (2 skipped), the Lit
suite passes 7 tests, and the build plus relative-asset check pass. The dated
[browser review](ui-lit-spike/browser-review.md) records the manual render and
reactivity fix; it does not satisfy the UI SDD's 92-case budget or HA matrix.

## Follow-up (2026-10-04)

The [local Supervisor/App lab](ha-app-lab.md) now rebuilds the checked-out App in
Home Assistant and verifies a healthy process running as UID 100. An authenticated
Home Assistant session lists the App as running and opens its Ingress panel, but
the frame stays blank/loading; the production UI route remains absent. This is
packaging and failure-state evidence, not a completed UI or platform matrix.

The ordinary offline suite passes **263 tests (2 skipped)**, specification
validation and `git diff --check` pass, and the isolated Lit suite passes all
7 tests plus type, boundary, build, and relative-asset checks. RepoWise's
safe-only dead-code pass reports **0 findings**. Its refactoring targets still
include runtime and copy/persistence hotspots; the coverage-gradient marker is
based on the existing index, not a fresh coverage measurement for this change.
A fresh Graphify code-only extraction contains **1,341 nodes and 3,498 edges**.
`OperationRepository` remains the largest hub at 57 edges. Its one-hop
dependents still include runtime HTTP/resources, copy/import execution, and
tests, so this lab increment leaves that contract untouched.

The Ingress follow-up adds a bounded, token-redacted Core-to-Supervisor smoke.
On the disposable lab it observes `401` without a session, `200` for health
and readiness with a session, and `404` for the current root route. The
ordinary suite passes **267 tests (2 skipped)** and the isolated Lit suite
still passes 7. RepoWise again reports **0 safe dead-code findings**; its
refactoring targets remain advisory. A fresh Graphify code-only graph has
**1,361 nodes and 3,535 edges**. `OperationRepository` is still first at
57 edges; the new `probe()` is called only by its lab CLI and tests, with no
domain/application dependency on Home Assistant.

The [GitHub Verify runs](https://github.com/vypdev/symphonia/actions/runs/37222603556)
for the Ingress increment succeeded, but annotated the Node 20 action-runtime
deprecation and the forthcoming `ubuntu-latest` image migration. The workflow
now uses the documented Node 24 compatible major versions of
[checkout](https://github.com/actions/checkout),
[setup-python](https://github.com/actions/setup-python), and
[setup-node](https://github.com/actions/setup-node), pins Ubuntu 24.04 for its
existing Linux jobs, and avoids persisting checkout credentials. The YAML
parses locally; the pushed workflow run is the compatibility check.
