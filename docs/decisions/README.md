# Architecture decision records

ADRs contain only decisions already justified and accepted by the product brief or owner clarification. Proposals and implementation choices remain in [open questions](../open-questions.md).

| ADR | Status | Decision |
| --- | --- | --- |
| [0001](0001-provider-independent-recording-domain.md) | Accepted | Provider-independent recording domain |
| [0002](0002-copy-and-sync-are-distinct.md) | Accepted | One-time copy and persistent sync are distinct concepts |
| [0003](0003-home-assistant-app-primary.md) | Accepted; OAuth clauses superseded by 0007 | Home Assistant App is the primary deployment boundary |
| [0004](0004-home-assistant-native-ui.md) | Accepted | App UI follows Home Assistant-native interaction and visual patterns through an owned compatibility layer |
| [0005](0005-lit-typescript-vite-ui.md) | Accepted | Future App presentation layer uses Lit, TypeScript, and Vite, subject to UI readiness gates |
| [0006](0006-narrow-home-assistant-playback-broker.md) | Accepted; OAuth-optional qualification superseded by 0007 | Home Assistant playback uses a narrow companion broker instead of broad App-to-Core authority |
| [0007](0007-home-assistant-oauth-companion.md) | Accepted authority direction; protocol gated | HA provider OAuth uses a thin native-flow companion; the App retains grants/refresh, with no Cloudflare/public App callback |
| [0008](0008-install-local-oauth-keys-and-backups.md) | Accepted key-custody direction; conformance gated | Automatic restart with install-local keys, encrypted Core identity backups and excluded App private keys |

An ADR is immutable after acceptance except for typo/link corrections. A changed decision gets a new ADR that supersedes the old one.
