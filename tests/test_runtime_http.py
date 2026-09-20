from __future__ import annotations

import unittest

from symphonia.infrastructure import OperationRepository
from symphonia.runtime.http import route_get


class RuntimeHTTPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = OperationRepository()

    def tearDown(self) -> None:
        self.repository.close()

    def test_health_and_readiness_are_public_runtime_checks(self) -> None:
        status, payload = route_get("/health", self.repository)
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")

        status, payload = route_get("/ready", self.repository)
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ready")

    def test_version_and_unknown_routes(self) -> None:
        status, payload = route_get("/version", self.repository)
        self.assertEqual(status, 200)
        self.assertIn("version", payload)

        status, payload = route_get("/admin", self.repository)
        self.assertEqual(status, 404)
        self.assertEqual(payload, {"error": "not_found"})

    def test_ingress_base_path_is_stripped_without_accepting_sibling_paths(self) -> None:
        status, payload = route_get(
            "/local_symphonia/ready?poll=1",
            self.repository,
            ingress_path="/local_symphonia",
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ready")

        status, payload = route_get(
            "/local_symphonia-extra/ready",
            self.repository,
            ingress_path="/local_symphonia",
        )
        self.assertEqual(status, 404)
        self.assertEqual(payload, {"error": "not_found"})

    def test_unsafe_ingress_base_path_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            route_get("/ready", self.repository, ingress_path="/bad/../path")


if __name__ == "__main__":
    unittest.main()
