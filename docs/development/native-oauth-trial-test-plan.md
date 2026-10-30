# Native OAuth trial verification

The [owning SDD](../../specs/native-oauth-validation-trial.md) defines 54 distinct
cases: 12 pure, 12 durable state, 12 adapters, 10 HTTP/UI and 8 package cases.
The [dated report](native-oauth-trial-acceptance-2026-10-30.md) separates actual
execution, research, manual UI review and owner/live acceptance.

## Architecture and deterministic checks

Pure policy and application use cases depend on semantic ports, not HA, HTTP,
SQLite or crypto frameworks. Ordinary tests exercise actual SQLite, AEAD and
loopback TLS where their case requires those adapters. Named fake providers,
HTTP responses, native actors and DNS routes are not evidence of live Spotify,
Core authentication or Supervisor routing.

```sh
python3 -m pip install -e '.[quality]'
make verify
make coverage
npm run validate:specifications
```

The ordinary suite executes 46 trial cases and skips the eight explicitly
privileged package cases. Root coverage remains at its existing 85% threshold.
Do not claim the eight skipped cases passed because ordinary CI is green.

## Exact package campaign

Use only the guarded disposable lab from [the lab guide](ha-app-lab.md).
Its devcontainer image and ownership label are checked before any mutation.
The matrix must be Core 2026.10.4, Supervisor 2026.10.5 and aarch64. A privileged
nested-Docker devcontainer is a laboratory dependency, never an owner App
permission. Loopback lab ports do not imply the App exposes host ports.

Prepare that lab with the existing operator, then run from a fresh output path:

```sh
PYTHONPATH=src:. SYMPHONIA_NATIVE_TRIAL_PACKAGE_LAB=1 \
SYMPHONIA_NATIVE_TRIAL_PACKAGE_OUTPUT=/tmp/symphonia-native-package-fresh \
python3 -m unittest tests.test_native_oauth_trial_packaging -v
```

The suite runs new observations; it does not accept an old receipt as a test run.
It requires the trial App stage to be absent. Unexpected existing artifacts
are preserved for explicit reconciliation, not overwritten. It installs the
same self-contained helper script into disposable Core, builds the App from its
committed manifest, exercises actual private DNS/CSR/mTLS, creates a synthetic
sealed grant via the test-only Provider port, performs a real Supervisor App-only
backup/restore, and retires its exact App, helper source, stage and backup.

The standalone Core campaign uses the pinned official Core image with no external
network. Docker maps the fixed private alias to loopback only in that campaign.
It loads the **installed** helper, uses real authenticated Core HTTP requests and
Core-signed callback state, and restarts the App in new child processes. The
provider is injected exclusively by the lab composition; the shipping entrypoint
has fixed Spotify URLs and no endpoint, proxy or fake-provider configuration.
The Supervisor campaign separately proves the actual alias and topology.

Supervisor-origin Ingress requests in the package campaign have synthetic identity
headers. They verify the App's origin/header gate, not a real browser HA session.
Actual My relay/browser and Spotify consent remain live acceptance obligations.

## Coverage and failure supplements

Use coverage 7.16.1 in the host quality environment and its pure tracer supplied
read-only to Core/App laboratory processes. The optional fixture coverage mount
requires the explicit evidence marker; no coverage package or hook is shipped
in the App. Aggregate ordinary, actual installed-helper/Core, App child-process
and shipping-entry-module measurements. Normalize only the known package source
paths, after verifying manifests match the measured source. Never merge coverage
from another revision or silently exclude uncovered production files.

Each of the twelve changed Python modules must reach at least 85% combined
line/branch coverage; new pure policy requires at least 90% branch coverage.
The shipping-main supplement uses a labeled, fresh Linux volume, verifies real
UID 10001, restarts, removes one synthetic wrapping key, confirms locked startup,
and checks a read-only startup failure. It deletes that owned volume afterward.
Shared macOS bind mounts are not a substitute for Linux ownership persistence.

Fault supplements exercise lost acknowledgements without mutation replay,
unknown outcome reporting, corrupted Core identity, explicit expired-key cleanup,
unsafe files/cache ownership, HTTP framing and cancellation during exchange.
They are explicitly injected adapter failures, not extra live-provider cases.

## Manual and owner acceptance

Review actual native forms and read-only status in Chrome: keyboard focus,
narrow layout, English/Spanish, disclosures, errors and observed state. An HTML
or translation assertion alone does not satisfy that review. Keep screenshots
with only synthetic data; never capture a real bootstrap block or callback URL
for public evidence.

Before owner installation, review clean source/package hashes, remote checks,
least privileges, encrypted future Core backups and scoped rollback. Applicable
browser action-time approval covers the exact experimental package and Core
restart. Then follow [the runbook](../operations/native-oauth-trial.md).
Only an observed owner/Core/My/Spotify journey, restart and confirmed same-account
refresh can close live acceptance. Record local retirement and external Spotify
grant revocation separately.
