# Symphonia Home Assistant App metadata

This directory is an experimental Supervisor App metadata scaffold. It follows
the App/service boundary used by `vypdev/homeassistant-gateway`:

- management traffic is Ingress-only (`8099` is not mapped as a direct port);
- only `/data` is persistent;
- the App requests no Home Assistant or Supervisor API access; and
- the service image runs the repository root `Dockerfile` as a non-root user.

The metadata is not a published release yet. The image reference, supported
architecture matrix, OAuth callback contract, Home Assistant-native UI,
backup/restore behavior and release signing still require their SDD gates
before stable publication. The future UI is governed by the
[Home Assistant-native UI foundation](../specs/home-assistant-native-ui.md); the
metadata scaffold does not imply that UI has been implemented.
