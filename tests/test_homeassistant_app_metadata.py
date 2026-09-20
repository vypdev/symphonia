from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class HomeAssistantAppMetadataTests(unittest.TestCase):
    def test_experimental_metadata_is_ingress_only_and_least_privilege(self) -> None:
        config = (ROOT / "addon" / "config.yaml").read_text(encoding="utf-8")
        self.assertIn("stage: experimental", config)
        self.assertIn("ingress: true", config)
        self.assertIn("ingress_port: 8099", config)
        self.assertIn("- data:rw", config)
        self.assertNotIn("ports:", config)
        self.assertNotIn("homeassistant_api:", config)
        self.assertNotIn("hassio_api:", config)

    def test_metadata_declares_only_the_architectures_of_the_experimental_matrix(self) -> None:
        config = (ROOT / "addon" / "config.yaml").read_text(encoding="utf-8")
        self.assertIn("  - amd64", config)
        self.assertIn("  - aarch64", config)
        self.assertNotIn("  - armv7", config)


if __name__ == "__main__":
    unittest.main()
