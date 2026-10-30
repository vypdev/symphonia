# Native OAuth trial: current-Core hook evidence, 2026-10-30

This report reruns the **existing research fixture**, not the proposed installable
trial or its 54 planned package cases. No real provider or owner configuration
participated. Design readiness is recorded separately in the owning SDD and
preparation review; the package remains unimplemented.

## Runtime and input identities

- Repository source: `8045f33f493a64e008332918e0c1cc671a98d8c6`.
- Official image tag: Home Assistant Core 2026.10.4.
- Immutable image digest: `sha256:23f4dfbb69ce76315dbc4de7915504f1c2dcecd7ca2648113a493a385972e133`.
- Image ID: `sha256:59160fc724d82aa83186f577f46aa8c8abe40af4052502eb32b621943582a5f6`.
- Actual runtime: Python 3.14.9 and cryptography 50.0.1.
- Result: exit 0, all 36 named observations true. Four named Ingress checks are
  explicitly stubbed; count is not a claim of 36 real Ingress or OAuth tests.
- Nonfatal runtime warning: rich segment module emits SyntaxWarning about return
  in finally; the campaign still completes successfully.

The container used no network, published ports, credentials, owner config or
persistent Docker volume. It ran read-only, UID/GID 10001, cap-drop ALL,
no-new-privileges, 1 GiB memory, two CPUs, pids limit 256 and a bounded 256 MiB
tmpfs. Repository and the diagnostic wrapper were read-only mounts. The wrapper
calls the unchanged research campaign and prints only versions, boolean results,
source hashes and sanitized failure locations. Container was automatically removed.

| Source | SHA-256 |
|---|---|
| `tools/ha_oauth_companion_lab/key_custody_probe.py` | `68bc9cfe5faa83dbb64b4ea225003d6458453def82499edb35a709435d3afa37` |
| `tools/ha_oauth_companion_lab/key_publication_probe.py` | `86d13e63e40ffac6b86e264bce84731ff54c3ac2991bfa5317af8b40c2e138d0` |
| `tools/ha_oauth_companion_lab/native_reset_probe.py` | `633b64f604a081c4c8f624194c6631709651a0ed3d4d608b70766860f704eed3` |
| `tools/ha_oauth_companion_lab/recovery_probe.py` | `d51f0c481262b6df7b2e43b9ceb3a5f25b4b291b557cfbd3f8bf73911f02f1df` |

## Observations and boundaries

The fixture uses actual Core authenticated HTTP, current request actor selection,
real signatures and disposable key/state files. It exercises disabled/revoked
actors and same-admin confirmation without touching owner accounts. Its Ingress,
browser, Origin and CSRF consumer is a named test stub. There is no actual My,
Spotify, final helper package, Supervisor backup or owner Chrome consent here.

| Observation | Result |
|---|---|
| `approval_and_private_key_absent_from_saved_files` | true |
| `approval_replay_refused` | true |
| `changed_purpose_refused` | true |
| `consumed_reset_cannot_resume` | true |
| `different_admin_cannot_adopt_request` | true |
| `disabled_admin_cannot_approve` | true |
| `expired_approval_refused` | true |
| `fresh_confirmation_same_actor` | true |
| `fresh_native_approval_resumes_interrupted_reset` | true |
| `fresh_request_selects_resume` | true |
| `fresh_same_admin_receives_signed_approval` | true |
| `interrupted_reset_approval_consumed` | true |
| `invalid_signature_refused` | true |
| `malformed_core_key_locks` | true |
| `missing_core_key_locks_without_rekey` | true |
| `native_nonadmin_denied` | true |
| `native_reset_retires_old_material` | true |
| `native_unauthenticated_denied` | true |
| `no_config_entry_created` | true |
| `nonsecret_history_retained` | true |
| `replaced_core_key_locks` | true |
| `resume_approval_single_use` | true |
| `resume_needs_fresh_same_admin` | true |
| `retirement_consumed_reset_cannot_resume` | true |
| `retirement_fresh_native_approval_resumes_interrupted_reset` | true |
| `retirement_fresh_request_selects_resume` | true |
| `retirement_interrupted_reset_approval_consumed` | true |
| `retirement_only_resume_never_rekeys` | true |
| `retirement_resume_approval_single_use` | true |
| `retirement_resume_needs_fresh_same_admin` | true |
| `revoked_login_cannot_approve` | true |
| `signed_native_approval_admits_reset_once` | true |
| `stub_other_actor` | true |
| `stub_other_browser` | true |
| `stub_wrong_csrf` | true |
| `stub_wrong_origin` | true |

## Pinned source review

Core OAuth helper at tag 2026.10.4, blob
`04d5c6313bb035362eb08e19ebd546a334f88346`, exposes per-instance PKCE verifier,
authorize URL and Core callback state. Default creation resolves a provider grant
and default session persists refreshed tokens: these paths must be trapped and
never called by the App-only helper. Main reconfigure must stage only through the
actual Core callback request and validated matching state, then require a NEW
authenticated native form submission for confirmation. Submitted flow/actor
objects or inherited background context are not authority.

Core HTTP module at tag 2026.10.4, blob
`4f9076ca407fc10de7d9a2b3896aac9650ca1788`, exports current_request and
KEY_HASS_USER. The proposed adapter must check active/current administrator on
each mutation, with no original-browser or login-continuity claim.

Supervisor Ingress API at tag 2026.10.5, blob
`2e3559531112c59070dca7c7aa5b7a972e129cbf`, enforces panel_admin in its backend,
filters client identity headers case-insensitively and supplies its own user data.
Its user record is cached; read-only Ingress context must not authorize native
exchange/refresh. App metadata must set panel_admin, and the private peer/base and
session boundary still needs actual packaged Supervisor tests.

Core Ingress proxy source at tag 2026.10.4, blob
`d2ca7316fa8a0d39d923fcac1e8fa7348c64c02c`, publicly routes to Supervisor where
Ingress session validation occurs. Its route token is not native actor authority.
These are source observations, not execution of the final package.

## Owner preflight and next acceptance gates

Read-only Chrome observed Core 2026.10.4, Supervisor 2026.10.5, HAOS 18.3 and
Frontend 20260930.5. The existing Terminal has sh, tar, sha256sum, base64, mv and
mkdir; python3 is missing. Its actual configuration mount is /homeassistant.
Use the existing tools for a narrow reviewed hash-manifest shell delivery; no
Terminal privilege expansion or Python installation is required by the design.
No owner software, configuration, consent, backup or restart changed in preflight.

Action-owned SDD publication completed at35adb63. The preparation document records
the subsequent contract review. Next run the54-case package campaign with the exact source artifacts, actual native callbacks,
TLS, process restart and Supervisor backup/locked restore. Exact-package and
applicable action-time approval precede owner installation. Only the separately
recorded live sequence can prove actual My/Spotify delivery and real refresh.

## Main reconfigure and callback execution

The separate reproducible research probe in `tools/ha_oauth_companion_lab/native_flow_probe.py` ran in the same networkless pinned Core2026.10.4 boundary. All22 observations passed. Its initial assertion expected an ordinary-user HTTP403; actual Core returned401. The corrected assertion accepts HTTP401/403 or a native denial with zero admissions; the observed successful campaign used401. No authorization behavior was relaxed.

The probe creates a safe-reference entry and uses the actual main reconfigure HTTP API, per-attempt PKCE generator, Core-signed state, actual public callback view, native flow resumption and a NEW authenticated confirmation request. Direct lookalike state injection and duplicate callbacks admit nothing. Different, ordinary, disabled and revoked actors cannot confirm. Default token resolver/session calls are explicit traps.

The My-enabled component flag and the App stage/admission port are explicit test fixtures. No actual My relay/browser, TLS, provider exchange, sealed grant, restart or backup is proved by this probe; it contributes zero of the54 final-package cases.

| Observation | Result |
|---|---|
| `actual_main_reconfigure_external_step` | true |
| `actual_pkce_uses_s256` | true |
| `completed_flow_cannot_admit_twice` | true |
| `completion_different_admin_denied` | true |
| `completion_disabled_admin_denied` | true |
| `completion_ordinary_user_denied` | true |
| `completion_revoked_login_denied` | true |
| `completion_unauthenticated_denied` | true |
| `core_entry_retains_only_safe_references` | true |
| `default_core_token_paths_never_called` | true |
| `duplicate_callback_cannot_confirm_or_restage` | true |
| `exact_my_redirect_generated` | true |
| `fresh_same_admin_native_post_admits_once` | true |
| `invalid_core_state_signature_refused` | true |
| `lookalike_state_direct_flow_post_refused` | true |
| `native_flow_resumes_to_confirmation_form` | true |
| `per_attempt_verifiers_and_challenges_distinct` | true |
| `public_callback_has_no_admin_authority` | true |
| `real_callback_route_stages_matching_state` | true |
| `setup_creates_only_safe_reference_entry` | true |
| `setup_unauthenticated_denied` | true |
| `synthetic_code_verifiers_absent_from_saved_files` | true |

Probe SHA-256: `881242ab5b4f549fbbfb7103c6ccb07eac89a71143b15ec1a2ee7b60e840223f`. No owner HA account is created or changed. Reproduce from the repository root:

```sh
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --user 10001:10001 \
  --memory 1g --cpus 2 --pids-limit 256 \
  --tmpfs /tmp:rw,nosuid,nodev,size=256m,mode=1777 \
  --mount "type=bind,source=$PWD/tools/ha_oauth_companion_lab/native_flow_probe.py,target=/probe.py,readonly" \
  --workdir /tmp --env PYTHONDONTWRITEBYTECODE=1 --entrypoint python3 \
  ghcr.io/home-assistant/home-assistant@sha256:23f4dfbb69ce76315dbc4de7915504f1c2dcecd7ca2648113a493a385972e133 \
  /probe.py
```
