from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from tools import ha_app_lab

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
    def test_commands_refuse_a_labelled_container_using_the_wrong_image(self) -> None:
        for command in ("stop", "ingress-smoke", "status"):
            with self.subTest(command=command), patch("sys.argv", ["ha_app_lab.py", command]), patch.object(
                ha_app_lab, "_container_details", return_value={"image": "unrelated:latest", "label": "ha-app", "running": "true"},
            ), patch.object(ha_app_lab, "_run") as run:
                with self.assertRaises(SystemExit) as result:
                    ha_app_lab.main()
                self.assertEqual(result.exception.code, 1)
                run.assert_not_called()

    def test_stop_accepts_the_exact_pinned_lab_container(self) -> None:
        with patch("sys.argv", ["ha_app_lab.py", "stop"]), patch.object(
            ha_app_lab, "_container_details", return_value={"image": DEVCONTAINER_IMAGE, "label": "ha-app", "running": "true"},
        ), patch.object(ha_app_lab, "_run") as run:
            self.assertEqual(ha_app_lab.main(), 0)
            run.assert_called_once_with("docker", "stop", CONTAINER)
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
