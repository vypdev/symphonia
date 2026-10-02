# Disposable playback evidence lab

**Status:** prepared configuration, not a completed live feasibility test

**Reviewed:** 2026-09-30

This lab prepares a dedicated [Home Assistant Container](https://www.home-assistant.io/installation/linux) and [Music Assistant server](https://www.music-assistant.io/installation/) for the [RG-007 matrix](../../open-questions.md#rg-007--listening-source-target-and-command-feasibility). It contains no provider credentials, player addresses, broker implementation or sample personal library. The owner will provide disposable accounts/devices later. Do **not** copy a production Home Assistant or Music Assistant database into these volumes.

CI runs `docker compose config` against `.env.example` without pulling images, starting services, or claiming a live test pass.

## Supervisor, App, and Ingress smoke lane

The repository also includes the maintained Home Assistant Apps devcontainer
profile at [`.devcontainer/devcontainer.json`](../../../.devcontainer/devcontainer.json).
It runs the official Supervisor development environment, rather than pretending
that Home Assistant Container provides Apps or Ingress. This is the local lane
for eventual App install, lifecycle, and Ingress smoke tests; it is configured
but has **not** yet been launched in this workspace.

The App metadata currently lives under `addon/`, while its build context and
`Dockerfile` live at the repository root. The staging helper bridges that
layout without moving or duplicating the source of truth: it copies only the
metadata, root `Dockerfile`, and `src/` into the devcontainer's local Apps
directory, and removes the published `image` setting from the generated local
metadata so Supervisor builds the checked-out source. It records exactly which
files it owns, refuses an unowned non-empty target, rejects unsafe manifest
paths, and removes only stale files from a prior managed stage.

On a development machine with VS Code, the Dev Containers extension, and a
working Docker Engine:

1. Open this repository and choose **Reopen in Container**.
2. Run **Terminal → Run Task → Start Home Assistant lab**. This stages Symphonia
   and starts the Supervisor devcontainer; Home Assistant is exposed at
   `http://localhost:7123`.
3. Complete onboarding with a disposable administrator, then run
   **Install Symphonia local App**. Verify the App starts and opens through
   Ingress; no provider account is needed for this packaging smoke.
4. After changing application code, run **Rebuild and start Symphonia local
   App** to refresh the staged source, rebuild, and inspect App logs.

The official Apps devcontainer needs `--privileged` and persistent Docker,
containerd, and Supervisor volumes. Treat it as a disposable development
environment: do not import a production HA backup or account credentials. Its
ports are forwarded only for local development. The profile can exercise
Supervisor/App/Ingress behavior, but it has no implemented playback broker and
does not prove physical-player discovery, Spotify, Music Assistant, YouTube
Music, backup/restore policy, or production support. A separate disposable
Linux host on the same flat network as test players is still required for
multicast/audio-path evidence; macOS container networking is not that proof.

The setup follows Home Assistant's [local App testing guide](https://developers.home-assistant.io/docs/apps/testing/)
and current [Apps example devcontainer](https://github.com/home-assistant/apps-example/blob/main/.devcontainer.json),
reviewed 2026-09-30. The files are statically tested in CI, but a real
Supervisor startup/install/Ingress pass remains pending because this workspace
currently has no accessible Docker daemon.

## Safety and limits

- Run only in a **disposable Linux VM or dedicated Linux test host** with Docker Engine and enough memory for both services. The official Home Assistant Container guide does not support Docker Desktop, and Music Assistant requires host/macvlan networking on the same flat LAN as physical players. A macOS/OrbStack dry run is not evidence of multicast discovery or audio delivery.
- This Compose file uses `network_mode: host`; Home Assistant follows its official container example with `privileged: true`. Thus ports 8123 and 8095 become reachable on the test host, not just inside the repository. Isolate the VM/host with a firewall and disposable admin identity, and inspect port conflicts before starting. Music Assistant receives no extra mount capabilities.
- Home Assistant Container has **no Supervisor, Apps or Ingress**. It can test Core Spotify/Music Assistant integration behavior, source/player observations and commands. It cannot close the Symphonia App packaging, Ingress-user attribution, App-to-Core network alias, pairing, or backup/restore gates. Use a separate Home Assistant OS/Supervisor-compatible environment for those; the official [local App testing guide](https://developers.home-assistant.io/docs/apps/testing/) describes a Supervisor devcontainer or real HAOS host.
- The image tags in `.env.example` are mutable bootstrap defaults, **not pinned evidence**. Before a dated live run, record image digest/version, HA integration version, MA server version, source provider version, account tier, hardware/player IDs, timezone, network topology and cleanup result in a private test log without secrets.

## Prepare and start on the disposable Linux host

Copy `.env.example` to `.env` in this directory and check or replace image references. Never put OAuth secrets or YouTube Music cookies in `.env`. Then, from this directory:

```text
docker compose --env-file .env config
docker compose --env-file .env up -d
docker compose --env-file .env ps
```

Open Home Assistant at `http://TEST_HOST:8123` and Music Assistant at `http://TEST_HOST:8095` through the isolated test network. Complete empty, disposable onboarding. Add the HA Music Assistant integration only after the MA server is running; then add test sources/players and Spotify after dedicated credentials/devices are provided. Do not install an unofficial YouTube Music source or export browser cookies until its risk/owner decision is accepted. The official MA [HA integration guide](https://www.music-assistant.io/integration/installation/) explains account/caller prerequisites.

Stop without deleting evidence volumes:

```text
docker compose --env-file .env down
```

Only on a confirmed disposable host, after saving the sanitized probe results and verifying the Compose project/volumes, remove this lab's volumes if desired. `down` alone intentionally retains them; no cleanup script or broad recursive delete is supplied.

## Evidence to capture later

Use [the full release matrix](../playback-release-gates.md) and [integration-source proof matrix](../../providers/playback-integration-source-review.md#rg-007-proof-matrix-before-release). For each profile, record: exact action, account/source/player/output identities (hashed or synthetic in shared reports), allowed capabilities, accepted/rejected response, independently observed effect, elapsed time, duplicate-name and idle behavior, restart/recovery, and cleanup. Record `unknown` when the test lacks a real account/device; do not convert an empty lab into a pass.
