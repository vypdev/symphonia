# Local Supervisor and App lab

**Observed:** 2026-10-04 on macOS/OrbStack ARM64. **Purpose:** repeatable, disposable App packaging, startup, authenticated Ingress, and operational dashboard smoke. This is not a supported Home Assistant deployment or a provider/playback test.

The host launcher follows Home Assistant's [local App testing guide](https://developers.home-assistant.io/docs/apps/testing/) and uses its [Apps devcontainer](https://github.com/home-assistant/apps-example/blob/main/.devcontainer.json). The devcontainer and Python staging sidecar are pinned to the digests in `tools/ha_app_lab.py`; the nested Supervisor channel still resolves its current platform images at startup. Record those versions for every live run.

## Run from the repository root

Docker Engine and Python 3 are required on the host. Run:

```text
python3 tools/ha_app_lab.py up
python3 tools/ha_app_lab.py status
python3 tools/ha_app_lab.py ingress-smoke
```

`up` creates or resumes the named `symphonia-ha-lab` devcontainer, stages only the checked-out App build inputs into its dedicated Supervisor volume, starts Supervisor if needed, installs or rebuilds `local_symphonia`, starts it, and waits for Docker health. It leaves onboarding to the person using the browser. Open `http://127.0.0.1:7123/` to create a **disposable** Home Assistant administrator; use no production backup or provider credentials. Build the production UI first with `cd ui && npm ci --ignore-scripts && npm run build` when changing its source. The built assets are checked into `src/symphonia/runtime/ui_assets/`; the Lit review fixture remains separate.

After source changes, run `up` again to restage and rebuild. `stage` only refreshes the local App source. `ingress-smoke` runs [the bounded probe](../../tools/ha_ingress_probe.py) inside the disposable Core container: it creates an internal Supervisor session, verifies that a missing cookie is denied, and checks `/health`, `/ready`, `/`, the built JavaScript asset, and `/api/dashboard` through the real Supervisor proxy. It prints only status codes and nonsecret service fields. It does not reuse or expose the browser administrator's session. `stop` stops the named devcontainer and **retains** the named Docker volumes. No reset/delete command is provided. `status` reports whether the lab container and Supervisor API are running. The launcher refuses to reuse or stop an unrelated container with the same name.

The lab's host ports bind to loopback: `7123 → 80` for the Home Assistant HTTP listener observed in this pinned devcontainer run, and `7357 → 4357` for the optional dev service. The official example lists `7123 → 8123`; in this 2026.9.4 Core run, port 8123 redirected to port 80 and could not serve onboarding through that mapping. Recheck the listener when changing the nested platform version. The host launcher mounts the checkout read-only; staging writes to a named Supervisor volume through the existing symlink/manifest-guarded helper in a networkless Python sidecar. It does not mount the host Docker socket into the devcontainer.

The devcontainer uses `--privileged` because the maintained Supervisor environment runs Docker inside Docker. On macOS/OrbStack, the launcher sets `SUPERVISOR_UNCONFINED=1` because the host lacks AppArmor. Supervisor consequently reports this lab as unsupported for production security assessment. Ports remain bound to `127.0.0.1`; use the lab for packaging and Ingress behavior only.

The VS Code tasks use `tools/stage_ha_local_app_in_devcontainer.sh`. The official Apps image contains Docker and the `ha` CLI but no Python interpreter, so that script runs the same pinned Python staging helper in a networkless nested sidecar. `tools/ha_app_lab.py` is the host-only path when VS Code/Dev Containers are unavailable.

## Dated smoke result

| Check | Result on 2026-10-04 | Remaining limit |
| --- | --- | --- |
| Devcontainer | Official `5-apps` digest `81ea6e6…` launched with separate Docker, containerd, and Supervisor volumes | Platform releases resolved by the beta channel can change |
| Supervisor and Core | Supervisor `2026.09.3`; Core `2026.9.4`; local App discovered after `ha store reload` | Supervisor reports unsupported on the macOS host because AppArmor is absent |
| Local App build | `local_symphonia` installed from staged source; published `image` setting removed only in staged metadata | This proves local build, not a published multiarch image |
| App startup | First start failed: Supervisor mounted `/data` as root, while the image ran as `symphonia` | Fixed by a narrow root initialization that owns `/data` and known SQLite files, then drops UID/GID before service execution |
| Restart after fix | App state `started`, Docker health `healthy`, service process UID `100`, SQLite database created under persistent App data | Full backup/restore and upgrade remain untested |
| Authenticated Home Assistant entry | Disposable administrator completed onboarding; Settings → Apps listed Symphonia as Running and Open Web UI opened its panel | This proves App discovery and the authenticated host entry point on this lab |
| Supervisor Ingress proxy | Internal Core session and cookie: no cookie `401`, `/health` `200`, `/ready` `200`, `/` `200`, built JS `200`, `/api/dashboard` `200` with `ready: true` | Proves the proxy reaches the built UI and API with a valid session; browser/user identity beyond Supervisor's session is not inferred |
| Direct peer protection | A Core-to-App request for `/api/dashboard` with a forged `X-Ingress-Path` returned `403` | The UI/API require the verified Supervisor peer on this lab |
| Ingress UI | Open Web UI rendered the dashboard in its iframe with real zero-state counts; Overview and Diagnostics navigation, manual Refresh timestamp change, light/dark toggle, and a narrow viewport were inspected in the in-app browser | This is one Core/Supervisor/browser visual and interaction pass, not the full UI foundation's supported matrix, screen-reader audit, or provider workflow |

For diagnostics without printing an Ingress token:

```text
docker exec symphonia-ha-lab ha supervisor info --raw-json
python3 tools/ha_app_lab.py ingress-smoke
docker exec symphonia-ha-lab ha apps logs local_symphonia
docker exec symphonia-ha-lab sh -lc 'tail -50 /mnt/supervisor/symphonia-supervisor-start.log'
```

The `ha apps info` response can contain a live Ingress entry token. Do not paste its raw output into shared issues or release evidence; record only state, version, and health. The authenticated browser reached the App panel through a `/api/hassio_ingress/…` iframe URL; the probe never emits its route token or session cookie. The [operational dashboard](../../specs/operational-dashboard.md) is the bounded, owner-approved first view. The broader [UI foundation](../../specs/home-assistant-native-ui.md) still requires host-context, browser-matrix, accessibility, and visual-reference proof.
