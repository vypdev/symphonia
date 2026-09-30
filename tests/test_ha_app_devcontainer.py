from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.stage_ha_local_app import stage_application


class HomeAssistantAppDevcontainerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "addon").mkdir()
        (self.project / "addon" / "config.yaml").write_text(
            "name: Symphonia\nslug: symphonia\nimage: example/image\narch:\n  - amd64\n",
            encoding="utf-8",
        )
        (self.project / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
        (self.project / "src" / "symphonia").mkdir(parents=True)
        (self.project / "src" / "symphonia" / "__init__.py").write_text(
            '"""test package"""\n', encoding="utf-8"
        )
        self.target = self.root / "supervisor" / "apps" / "local" / "symphonia"

    def test_stages_local_build_without_published_image(self) -> None:
        staged = stage_application(self.project, self.target)

        config = (self.target / "config.yaml").read_text(encoding="utf-8")
        self.assertNotIn("image:", config)
        self.assertIn("slug: symphonia", config)
        self.assertEqual(
            (self.target / "Dockerfile").read_text(encoding="utf-8"),
            "FROM python:3.12-slim\n",
        )
        self.assertTrue((self.target / "src" / "symphonia" / "__init__.py").is_file())
        self.assertIn("config.yaml", staged)

    def test_update_removes_stale_managed_files_and_preserves_unowned_files(self) -> None:
        stage_application(self.project, self.target)
        (self.target / "operator-note.txt").write_text("keep", encoding="utf-8")
        obsolete = self.project / "src" / "symphonia" / "obsolete.py"
        obsolete.write_text("old", encoding="utf-8")
        stage_application(self.project, self.target)
        obsolete.unlink()

        stage_application(self.project, self.target)

        self.assertFalse((self.target / "src" / "symphonia" / "obsolete.py").exists())
        self.assertEqual(
            (self.target / "operator-note.txt").read_text(encoding="utf-8"), "keep"
        )

    def test_refuses_nonempty_unowned_target(self) -> None:
        self.target.mkdir(parents=True)
        sentinel = self.target / "keep.txt"
        sentinel.write_text("user data", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "unowned App directory"):
            stage_application(self.project, self.target)

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "user data")

    def test_rejects_repository_overlap(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside the source repository"):
            stage_application(self.project, self.project)
        with self.assertRaisesRegex(ValueError, "outside the source repository"):
            stage_application(self.project, self.project.parent)

    def test_refuses_a_symlink_as_the_staging_target(self) -> None:
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        self.target.parent.mkdir(parents=True)
        self.target.symlink_to(elsewhere, target_is_directory=True)

        with self.assertRaisesRegex(ValueError, "must not be a symlink"):
            stage_application(self.project, self.target)

        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_rejects_unsafe_manifest_path_before_deleting_anything(self) -> None:
        self.target.mkdir(parents=True)
        marker = self.target / ".symphonia-devcontainer-stage.json"
        marker.write_text(json.dumps({"managed_files": ["../../keep.txt"]}), encoding="utf-8")
        sentinel = self.root / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "unsafe staging manifest path"):
            stage_application(self.project, self.target)

        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_interrupted_stage_manifest_can_be_resumed(self) -> None:
        previous = stage_application(self.project, self.target)
        new_source = self.project / "src" / "symphonia" / "new_module.py"
        new_source.write_text("VALUE = 1\n", encoding="utf-8")
        marker = self.target / ".symphonia-devcontainer-stage.json"
        marker.write_text(
            json.dumps({"managed_files": sorted((*previous, "src/symphonia/new_module.py"))}),
            encoding="utf-8",
        )

        stage_application(self.project, self.target)

        self.assertEqual(
            (self.target / "src" / "symphonia" / "new_module.py").read_text(
                encoding="utf-8"
            ),
            "VALUE = 1\n",
        )

    def test_devcontainer_is_the_official_privileged_supervisor_lab_profile(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = json.loads(
            (root / ".devcontainer" / "devcontainer.json").read_text(encoding="utf-8")
        )

        self.assertEqual(config["image"], "ghcr.io/home-assistant/devcontainer:5-apps")
        self.assertIn("--privileged", config["runArgs"])
        self.assertIn("7123:8123", config["appPort"])
        self.assertEqual(config["containerEnv"]["SUPERVISOR_CHANNEL"], "beta")

    def test_tasks_stage_sources_before_install_or_rebuild(self) -> None:
        root = Path(__file__).resolve().parents[1]
        tasks = json.loads((root / ".vscode" / "tasks.json").read_text(encoding="utf-8"))
        by_label = {task["label"]: task["command"] for task in tasks["tasks"]}

        self.assertIn(
            "python tools/stage_ha_local_app.py && ha apps install local_symphonia",
            by_label["Install Symphonia local App"],
        )
        self.assertIn(
            "python tools/stage_ha_local_app.py && ha apps rebuild --force local_symphonia",
            by_label["Rebuild and start Symphonia local App"],
        )


if __name__ == "__main__":
    unittest.main()
