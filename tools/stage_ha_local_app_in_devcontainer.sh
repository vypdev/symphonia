#!/bin/sh
# The official Apps devcontainer contains Docker, but no Python interpreter.
# Run the guarded Python staging helper in a pinned, networkless sidecar.
set -eu

workspace=${WORKSPACE_DIRECTORY:-/workspaces/symphonia}
test -d /mnt/supervisor
test -f "$workspace/tools/stage_ha_local_app.py"

docker run --rm --network none \
  --mount "type=bind,source=$workspace,target=/workspaces/symphonia,readonly" \
  --mount type=bind,source=/mnt/supervisor,target=/mnt/supervisor \
  --workdir /workspaces/symphonia \
  docker.io/library/python@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d \
  python tools/stage_ha_local_app.py
