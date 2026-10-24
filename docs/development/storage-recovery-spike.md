# SQLite recovery and backup spike

**Status:** research evidence only
**Last reviewed:** 2026-09-26

The repository now contains a small offline spike at
[`tools/storage_recovery_spike.py`](../../tools/storage_recovery_spike.py). It
creates a disposable persistent runtime, queues a bounded number of operations,
claims one ordinary lease and one cancellation-requested lease, closes the
runtime, reopens it as a different worker, waits until both leases have expired,
then verifies that the ordinary lease is reclaimed while the cancelled
operation is quarantined in `waiting_user` and cannot be resumed. It completes
the ordinary operation, then creates and validates an online SQLite backup
containing both recovery outcomes.

Run it from the repository root with:

```text
PYTHONPATH=src:. python3 tools/storage_recovery_spike.py --operations 1000 --payload-bytes 256
```

The JSON result reports the configured fixture count plus one dedicated
cancellation fixture, ordinary and cancellation-recovery state evidence,
SQLite version, file sizes, backup validity, total elapsed time, and separate
timings for runtime open, operation creation, claim/recovery, cancellation
fixture setup, checkpoint, and backup creation/validation. It contains no
database path, operation payload, account identifier, or credential. Timings
are observations for the machine and fixture size used; they are not product
SLOs or a restore benchmark.

`--payload-bytes` adds only repeated synthetic padding to each queued operation
so storage and write timings can be sampled at several fixture sizes. Runs are
capped at 64 MiB of total synthetic payload; the padding is not a model of real
playlist contents, and the cap is tooling protection rather than a product
limit.

This spike supports the foundation claims that operation leases survive a
process restart, cancellation-requested expired leases are not resumed as
ordinary work, and the composed runtime can produce a structurally validated
backup. The unit suite also reopens a backup containing operation, provider-connection, and
authorization-attempt rows through the normal runtime composition root and
readiness now fails closed when durable state contains invalid JSON or enum
values. The cancellation scenario is repository-level evidence only: it does
not exercise a provider API, prove provider reconciliation, or provide
authenticated operator resolution. The spike does not yet select backup
retention, encryption, Supervisor backup declarations, restore UX, or a
production scheduler. Those remain part of the App runtime and durable
execution SDD gates.
