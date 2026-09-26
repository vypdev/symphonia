# Direct App OAuth callback spike

**Status:** research prototype; not production authorization code
**Reviewed:** 2026-09-22

This spike follows the App-plus-Ingress direction used by Symphonia's primary
deployment model. Provider adapters remain inside the App. A future companion
integration is not required for the MVP authorization path.

## What it proves locally

- callback state resolves from a durable SHA-256 digest after repository restart;
- the callback is single-use and provider-bound before consumption;
- denial becomes a terminal attempt state without persisting provider error text;
- unknown paths, duplicate state parameters, replay, and wrong-provider callbacks fail safely;
- the HTTP prototype exposes only the configured callback route and refuses broad
  host binding by default; and
- the response never reflects authorization codes or provider error descriptions.

The transient authorization code is returned only to the in-process exchange
owner and is marked non-representational in the prototype result. A future
provider adapter must exchange it immediately, keep the resulting grant behind
the secret boundary, and never place either value in logs, URLs, diagnostics,
ordinary operation payloads, or backups.

## Still required before production

`RG-002` remains open. A Home Assistant test matrix must verify externally
reachable HTTPS redirects, arbitrary Ingress paths, remote access, browser
session continuity, user-provided client registrations, PKCE where applicable,
refresh/revocation, restart at every attempt phase, and callback-listener
isolation in the actual App network topology. The loopback-only server in this
spike is deliberately insufficient evidence for those claims.
