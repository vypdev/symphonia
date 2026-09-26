from __future__ import annotations

from io import BytesIO
import http.client
from pathlib import Path
import tempfile
import threading
import unittest

from symphonia.infrastructure import OperationRepository
from symphonia.runtime.http import SymphoniaRequestHandler, create_server, route_get


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
        for ingress_path in ("/bad/../path", "/local_symphonia?query", "/local\x00symphonia"):
            with self.assertRaises(ValueError):
                route_get("/ready", self.repository, ingress_path=ingress_path)

    def test_readiness_can_use_the_composed_runtime_healthcheck(self) -> None:
        status, payload = route_get("/ready", self.repository, readiness_check=lambda: False)

        self.assertEqual(status, 503)
        self.assertEqual(payload["status"], "not_ready")

    def test_json_surface_sets_no_cache_and_content_sniffing_headers(self) -> None:
        class FakeHandler:
            def __init__(self) -> None:
                self.status = None
                self.headers = {}
                self.wfile = BytesIO()

            def send_response(self, status: int) -> None:
                self.status = status

            def send_header(self, name: str, value: str) -> None:
                self.headers[name] = value

            def end_headers(self) -> None:
                return

        handler = FakeHandler()
        SymphoniaRequestHandler._json(handler, 200, {"status": "ok"})  # type: ignore[arg-type]

        self.assertEqual(handler.status, 200)
        self.assertEqual(handler.headers["Cache-Control"], "no-store")
        self.assertEqual(handler.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(handler.headers["Referrer-Policy"], "no-referrer")

    def test_json_surface_rejects_non_standard_numbers(self) -> None:
        class FakeHandler:
            def __init__(self) -> None:
                self.wfile = BytesIO()

            def send_response(self, status: int) -> None:
                return

            def send_header(self, name: str, value: str) -> None:
                return

            def end_headers(self) -> None:
                return

        with self.assertRaises(ValueError):
            SymphoniaRequestHandler._json(  # type: ignore[arg-type]
                FakeHandler(),
                200,
                {"value": float("nan")},
            )

    def test_composed_runtime_http_smoke_exposes_health_and_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            try:
                server = create_server(
                    host="127.0.0.1",
                    port=0,
                    database_path=str(Path(directory) / "symphonia.sqlite3"),
                    ingress_path="/symphonia",
                )
            except PermissionError:
                self.skipTest("the test sandbox does not permit local socket binding")

            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                connection = http.client.HTTPConnection(host, port, timeout=2)
                try:
                    connection.request("GET", "/symphonia/health")
                    health = connection.getresponse()
                    health_body = health.read().decode("utf-8")
                    connection.request("GET", "/symphonia/ready")
                    ready = connection.getresponse()
                    ready_body = ready.read().decode("utf-8")
                finally:
                    connection.close()

                self.assertEqual(health.status, 200)
                self.assertIn('"status": "ok"', health_body)
                self.assertEqual(ready.status, 200)
                self.assertIn('"status": "ready"', ready_body)
            finally:
                server.shutdown()
                server.server_close()
                server.close_resources()
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
