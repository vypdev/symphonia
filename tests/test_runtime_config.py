from __future__ import annotations

import unittest

from symphonia.runtime import RuntimeConfig


class RuntimeConfigTests(unittest.TestCase):
    def test_defaults_are_stable_for_local_runtime(self) -> None:
        config = RuntimeConfig()

        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 8099)
        self.assertEqual(config.database_path, "./symphonia.sqlite3")
        self.assertEqual(config.ingress_path, "/")

    def test_environment_values_are_parsed_and_normalized(self) -> None:
        config = RuntimeConfig.from_environment(
            {
                "SYMPHONIA_HOST": "  0.0.0.0 ",
                "SYMPHONIA_PORT": "8100",
                "SYMPHONIA_DATABASE": " /data/symphonia.sqlite3 ",
                "SYMPHONIA_INGRESS_PATH": "/local_symphonia/",
            }
        )

        self.assertEqual(config.host, "0.0.0.0")
        self.assertEqual(config.port, 8100)
        self.assertEqual(config.database_path, "/data/symphonia.sqlite3")
        self.assertEqual(config.ingress_path, "/local_symphonia")

    def test_invalid_configuration_fails_before_runtime_start(self) -> None:
        invalid_values = (
            {"port": 0},
            {"port": 65_536},
            {"port": "not-a-number"},
            {"host": "host with spaces"},
            {"database_path": "   "},
            {"database_path": "bad\x00path"},
            {"database_path": "bad\npath"},
            {"ingress_path": "relative"},
            {"ingress_path": "/bad/../path"},
            {"ingress_path": "/local_symphonia?query"},
            {"ingress_path": 1},
        )
        for values in invalid_values:
            with self.subTest(values=values), self.assertRaises(ValueError):
                RuntimeConfig(**values)

        with self.assertRaisesRegex(ValueError, "port"):
            RuntimeConfig.from_environment({"SYMPHONIA_PORT": "invalid"})

    def test_rejects_invalid_host_and_non_integral_port(self) -> None:
        for values in (
            {"host": "127.0.0.1\x00"},
            {"port": True},
            {"port": 8099.5},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                RuntimeConfig(**values)


if __name__ == "__main__":
    unittest.main()
