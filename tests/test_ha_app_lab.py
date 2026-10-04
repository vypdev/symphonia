from __future__ import annotations

from pathlib import Path
import unittest

from tools.ha_app_lab import (
    CONTAINER,
    DEVCONTAINER_IMAGE,
    STAGING_IMAGE,
    SUPERVISOR_VOLUME,
    app_is_installed,
    container_command,
    stage_command,
)


class HomeAssistantAppLabCommandTests(unittest.TestCase):
    def test_container_has_isolated_storage_and_loopback_ports(self) -> None:
        command = container_command(Path("/tmp/example-project"))

        self.assertEqual(command[:5], ["docker", "run", "--detach", "--name", CONTAINER])
        self.assertIn("127.0.0.1:7123:80", command)
        self.assertIn("127.0.0.1:7357:4357", command)
        self.assertIn("type=volume,source=symphonia-ha-lab-docker,target=/var/lib/docker", command)
        self.assertIn(f"type=volume,source={SUPERVISOR_VOLUME},target=/mnt/supervisor", command)
        self.assertIn("type=bind,source=/tmp/example-project,target=/workspaces/symphonia,readonly", command)
        self.assertNotIn("/var/run/docker.sock", " ".join(command))
        self.assertEqual(command[-1], DEVCONTAINER_IMAGE)

    def test_staging_has_no_network_and_uses_own_volume(self) -> None:
        command = stage_command(Path("/tmp/example-project"))

        self.assertIn("none", command)
        self.assertIn("type=bind,source=/tmp/example-project,target=/workspaces/symphonia,readonly", command)
        self.assertIn(f"type=volume,source={SUPERVISOR_VOLUME},target=/mnt/supervisor", command)
        self.assertEqual(command[-3:], [STAGING_IMAGE, "python", "tools/stage_ha_local_app.py"])

    def test_installed_app_response_omits_store_boolean(self) -> None:
        self.assertFalse(app_is_installed({"installed": False, "version": None}))
        self.assertTrue(app_is_installed({"state": "started", "version": "0.1.0"}))


if __name__ == "__main__":
    unittest.main()
