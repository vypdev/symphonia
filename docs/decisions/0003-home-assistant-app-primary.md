# ADR 0003: Home Assistant App is the primary deployment boundary

- **Status:** accepted
- **Date:** 2026-09-20
- **Last reviewed:** 2026-09-22

## Context

Symphonia is intended to run continuously in a homelab and integrate deeply with Home Assistant. The owner clarified that it will be implemented as a Home Assistant app/service following the pattern established by `vypdev/homeassistant-gateway`.

Home Assistant Supervisor provides an install/update lifecycle, Ingress UI authentication, persistent App data, backups, and a natural future integration surface. At the same time, music identity, provider access, jobs, and copy policy do not inherently belong to Home Assistant and must remain testable and usable independently.

## Decision

The primary supported distribution is a Supervisor-managed Home Assistant App installed from a Home Assistant App repository. It owns the long-running Symphonia service, durable jobs, provider connections, persistence, and management UI exposed through Ingress.

The implementation follows the `vypdev/homeassistant-gateway` deployment
pattern: the App is the product boundary and Ingress is the administrative
entry point. Provider authorization is owned by the App's provider adapters;
the MVP does not require a companion integration to broker OAuth. A companion
integration remains a later, optional native-surface extension.

The domain and application core remain independent of Home Assistant. A standalone composition profile will use the same core so the product can operate without Home Assistant and tests do not require it. Timing of the standalone release remains open.

A companion Home Assistant custom integration may later expose native entities, actions, and events over a stable authenticated service contract. It will not duplicate domain policy or access the database/secrets directly.

## Alternatives considered

### Standalone service first with Home Assistant added later

Rejected as the primary direction because it postpones the owner's intended installation, lifecycle, Ingress, and homelab experience.

### Put all logic in a custom integration

Rejected because long-running provider jobs, complex UI, dependency isolation, and durable service storage fit an App better, while custom integration lifecycle would couple the domain to Home Assistant Core.

### Require Home Assistant in core modules

Rejected because it damages testability, standalone usability, and architectural separation without improving provider/domain behavior.

### App calls Home Assistant directly for every native feature

Not selected. A companion integration, MQTT, and direct APIs need an RFC. Native surfaces should not force service policy into Home Assistant adapters.

## Consequences

Positive:

- installation, startup, UI authentication, updates, backups, and persistence fit the target homelab;
- Home Assistant users get a first-class operational experience;
- a companion integration can remain thin and native;
- core logic remains portable and testable.

Trade-offs:

- Ingress-relative routing and provider OAuth callbacks need explicit design and testing;
- Home Assistant OS/Supervised becomes the primary release matrix;
- standalone mode needs its own authentication/network boundary;
- App and optional integration artifacts need version compatibility;
- provider credentials in Supervisor backups require a deliberate encryption/key/restore model.
