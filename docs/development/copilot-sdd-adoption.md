# Copilot SDD adoption

Symphonia follows the supported Copilot specification system from 2026-10-29.
Read the [standard](../../specs/README.md), start from the
[template](../../specs/_template.md), and consult the
[generated inventory](../../specs/CATALOG.md). Proposed changes to that system
belong in a new [Copilot issue](https://github.com/vypdev/copilot/issues/new/choose).
Do not introduce another catalog dialect, validator policy, or publication path.

```text
Copilot standard/template → owning SDD + SDK v1 catalog
                         → original validator → generated CATALOG.md
                         → normal Action publication and protected PR checks
```

The diagram means that a contributor updates the owning contract and catalog,
runs the original validator, regenerates the index when metadata changes, and
uses the installed Action workflow. Local checks do not replace remote gates.

## Commands and provenance

Node.js 24 or later is required for specification tooling; application Python
requirements are unchanged. No root JavaScript dependencies are needed.

```sh
npm run generate:specifications
npm run validate:specifications
PYTHONPATH=. python tools/validate_specs.py
```

The same package scripts support the standard's `pnpm run` commands. The Python
entrypoint only invokes Copilot; it does not maintain a second schema or renderer.
CI provisions Node.js in both Python test and coverage jobs. Copilot verification
continues using the existing trusted setup and runtime prerequisites.

The standard, template, catalog validator and path policy are unchanged copies
from Copilot 3.10.6, commit
[`f5e5a4c`](https://github.com/vypdev/copilot/tree/f5e5a4cf9a80248994469cd88ad55eecab5b95ca).
The [provenance manifest](../../tools/copilot-specifications/provenance.json)
records upstream paths and Git blob hashes; the upstream
[MIT license](../../tools/copilot-specifications/LICENSE) is retained. The consumer
entrypoint supplies this repository's root to the original exported validator.
An upstream update must replace reviewed source copies and hashes together,
then rerun the original checks and consumer regressions. Do not patch policy
locally to make an incompatible catalog pass.

## Inventory and evidence limits

The catalog has Copilot's `version`, `capabilities`, SDK metadata and six evidence
arrays: `specs`, `workflows`, `entrypoints`, `code`, `tests`, `documentation`.
Its supported statuses are `proposed`, `implemented`, `as-built-baseline`, and
`deprecated`. The former local JSON Schema and custom status renderer are retired.

Nine prospective capabilities are `proposed`. Their owning documents retain
`Draft` or `Ready for review`, existing requirement identifiers, decisions,
blockers, acceptance scenarios and numeric budgets. The bounded read-only
dashboard alone retains `implemented`. Inventory status describes the capability;
design readiness and permission to implement remain explicit in the SDD and
owner review, as required by the standard.

`lastVerified: 2026-10-29` is a source/path migration audit. It does not claim that
every planned acceptance case ran on that date, that a whole capability is
implemented, or that live Home Assistant/Spotify acceptance succeeded. Source,
test and documentation paths cover foundations or research where the capability
is still proposed. In particular:

| Capability | Existing executable evidence | Limit |
|---|---|---|
| Playback control | Disposable Compose configuration; `playback-lab-config` CI job | Configuration validity only; no player/broker implementation or live provider proof |
| OAuth companion | Core/transport/key/recovery probes and fixture tests | Isolated laboratory proof; no installed production helper or completed owner-instance OAuth |
| UI foundation | Shared theme, boundary checks and UI entrypoint | Full component/browser/visual matrix remains pending |
| Recording identity | Normalization module and identity tests | No complete scoring/resolver or labeled-corpus acceptance |

Each owning SDD includes its former catalog requirement inventory and exact
blocker text. Historical reports retain their dates and past results; references
to the former catalog in those reports describe the past. The twenty numbered
headings now match the canonical template, with old heading anchors retained.
No application or OAuth deployment behavior changes in this migration.

## Readiness review

The original catalog check validates inventory, ownership, paths and generated
output; it cannot establish every normative product requirement. Before declaring
`Ready for implementation`, apply every review question in section 8 of the
standard and the owning SDD's Definition of Done. Reviewers must verify:

1. Current evidence, user flows and concrete states, including failure/recovery.
2. Defaults, limits, architecture boundaries, security and privacy.
3. Numeric case allocation, acceptance and requirement traceability.
4. Setup/user/operator/contributor documentation, compatibility and rollback.
5. Resolution of material blockers and explicit owner approval to implement.

These are the standard's human review gates, not a parallel machine contract.
Structural validation must never change `Draft` to ready automatically or count
planned tests as executed evidence.

## Tracking

Local validation on 2026-10-29 used Python 3.11.15 and Node 24.22.2:

| Check | Result |
|---|---|
| Original Copilot SDK catalog reader | `sdk-v1`, all 10 capabilities accepted |
| Original Copilot retained-owner SDD format check | All 10 owning documents accepted |
| Original catalog validator/generator | 10 capabilities; generated index current |
| Consumer regressions | 12 cases, including unchanged upstream blob hashes, ownership, paths, statuses and stale-index rejection |
| `make verify` / `make coverage` | 565 Python tests; 89% combined line/branch coverage, above the unchanged 85% floor |
| UI typecheck / tests / build | Passed; 27 tests; committed App assets reproduced exactly |

The old custom-dialect validator assertions were replaced by SDK consumer
regressions; application tests were retained. All previous catalog requirement
IDs and exact blocker strings were checked against the owning documents during
migration. Remote CI and normal Action admission remain separate gates; the
local results do not establish live OAuth acceptance.

- Migration: [Symphonia #33](https://github.com/vypdev/symphonia/issues/33).
- Superseded dialect-adapter request:
  [Copilot #786](https://github.com/vypdev/copilot/issues/786), closed not planned.
- Installation guidance request:
  [Copilot #787](https://github.com/vypdev/copilot/issues/787).
- Real OAuth follow-up remains [Symphonia #32](https://github.com/vypdev/symphonia/issues/32)
  and must use normal Action admission after the compatible base is merged.
