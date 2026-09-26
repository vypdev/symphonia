# SQLite recovery and backup spike

**Status:** research evidence only
**Last reviewed:** 2026-09-22

The repository now contains a small offline spike at
[`tools/storage_recovery_spike.py`](../../tools/storage_recovery_spike.py). It
creates a disposable persistent runtime, queues a bounded number of operations,
claims one lease, closes the runtime, reopens it as a different worker, waits
until the lease has expired, reclaims and completes the operation, then creates
and validates an online SQLite backup.

Run it from the repository root with:

```text
PYTHONPATH=src:. python3 tools/storage_recovery_spike.py --operations 1000
```

The JSON result reports only fixture counts, state transition evidence, SQLite
version, file sizes, backup validity, total elapsed time, and separate timings
for runtime open, operation creation, claim/recovery, checkpoint, and backup
creation/validation. It contains no database path, operation payload, account
identifier, or credential. Timings are observations for the machine and
fixture size used; they are not product SLOs or a restore benchmark.

This spike supports the foundation claims that operation leases survive a
process restart, concurrent SQLite workers respect the lease boundary, and
the composed runtime can produce a structurally validated backup. The unit
suite also reopens a backup containing operation, provider-connection, and
authorization-attempt rows through the normal runtime composition root and
readiness now fails closed when durable state contains invalid JSON or enum
values. It does not yet select backup retention, encryption,
Supervisor backup declarations, restore UX, or a production scheduler. Those
remain part of the App runtime and durable execution SDD gates.
