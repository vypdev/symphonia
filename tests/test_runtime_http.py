from __future__ import annotations

from io import BytesIO
import http.client
from pathlib import Path
import socket
import tempfile
import threading
from types import SimpleNamespace
import unittest

from symphonia.infrastructure import OperationRepository
from symphonia.runtime.http import (
    SymphoniaHTTPServer,
    SymphoniaRequestHandler,
    create_server,
    route_get,
)


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

    def test_readiness_exception_fails_closed_without_exposing_detail(self) -> None:
        def broken_readiness() -> bool:
            raise RuntimeError("secret database detail")

        status, payload = route_get(
            "/ready", self.repository, readiness_check=broken_readiness
        )

        self.assertEqual(status, 503)
        self.assertEqual(payload, {"service": "symphonia", "status": "not_ready"})
        self.assertNotIn("secret", str(payload))

    def test_non_origin_and_cross_ingress_paths_never_route_to_health(self) -> None:
        for path in (
            "health",
            "//other-host/health",
            "https://other-host/health",
            "/local_symphonia/health#fragment",
            "/local_symphonia-extra/health",
            "/other/health",
        ):
            with self.subTest(path=path):
                status, payload = route_get(
                    path, self.repository, ingress_path="/local_symphonia"
                )
                self.assertEqual((status, payload), (404, {"error": "not_found"}))

    def test_dashboard_dispatch_requires_the_socket_peer_under_an_ingress_prefix(self) -> None:
        class FakeHandler:
            server = SimpleNamespace(
                ingress_path="/symphonia",
                repository=self.repository,
                service_version="0.1.0",
                readiness_check=self.repository.healthcheck,
            )

            def __init__(self, path: str, peer: str) -> None:
                self.path = path
                self.client_address = (peer, 1234)
                self.calls: list[tuple[object, ...]] = []

            def _dashboard(self) -> None:
                self.calls.append(("dashboard",))

            def _asset(self, relative: str) -> None:
                self.calls.append(("asset", relative))

            def _json(self, status: int, payload: dict[str, object]) -> None:
                self.calls.append(("json", status, payload))

        for path, expected in (
            ("/symphonia/", ("asset", "/")),
            ("/symphonia/assets/app.js", ("asset", "/assets/app.js")),
            ("/symphonia/api/dashboard", ("dashboard",)),
        ):
            with self.subTest(path=path):
                handler = FakeHandler(path, "172.30.32.2")
                SymphoniaRequestHandler.do_GET(handler)  # type: ignore[arg-type]
                self.assertEqual(handler.calls, [expected])

        denied = FakeHandler("/symphonia/api/dashboard", "127.0.0.1")
        SymphoniaRequestHandler.do_GET(denied)  # type: ignore[arg-type]
        self.assertEqual(denied.calls, [("json", 403, {"error": "forbidden"})])

        public = FakeHandler("/symphonia/ready", "127.0.0.1")
        SymphoniaRequestHandler.do_GET(public)  # type: ignore[arg-type]
        self.assertEqual(public.calls[0][:2], ("json", 200))

        sibling = FakeHandler("/symphonia-extra/api/dashboard", "172.30.32.2")
        SymphoniaRequestHandler.do_GET(sibling)  # type: ignore[arg-type]
        self.assertEqual(sibling.calls, [("json", 404, {"error": "not_found"})])

    def test_server_configuration_rejects_missing_or_conflicting_store(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be supplied"):
            SymphoniaHTTPServer(("127.0.0.1", 0))
        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            SymphoniaHTTPServer(
                ("127.0.0.1", 0),
                repository=self.repository,
                resources=object(),  # type: ignore[arg-type]
            )

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

    def test_json_surface_closes_connection_on_disconnected_client(self) -> None:
        class DisconnectedWriter:
            def write(self, body: bytes) -> None:
                raise ConnectionError("client disconnected")

        class FakeHandler:
            close_connection = False
            wfile = DisconnectedWriter()

            def send_response(self, status: int) -> None:
                return

            def send_header(self, name: str, value: str) -> None:
                return

            def end_headers(self) -> None:
                return

        handler = FakeHandler()
        SymphoniaRequestHandler._json(handler, 200, {"status": "ok"})  # type: ignore[arg-type]
        self.assertTrue(handler.close_connection)

    def test_method_errors_have_bounded_json_categories(self) -> None:
        class FakeHandler:
            def __init__(self) -> None:
                self.result: tuple[int, dict[str, str], bool] | None = None

            def _json(
                self, status: int, payload: dict[str, str], *, close_connection: bool
            ) -> None:
                self.result = (status, payload, close_connection)

        for code, category in ((400, "bad_request"), (501, "not_implemented"), (503, "server_error")):
            with self.subTest(code=code):
                handler = FakeHandler()
                SymphoniaRequestHandler.send_error(  # type: ignore[arg-type]
                    handler,
                    code,
                    message="secret request detail",
                    explain="internal stack",
                )
                self.assertEqual(handler.result, (code, {"error": category}, True))

    def test_composed_runtime_http_smoke_exposes_health_and_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    probe.bind(("127.0.0.1", 0))
                    port = probe.getsockname()[1]
                server = create_server(
                    host="127.0.0.1",
                    port=port,
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
                    connection.request("GET", "/symphonia/")
                    denied_root = connection.getresponse()
                    denied_root.read()
                    connection.request("GET", "/symphonia/api/dashboard", headers={"X-Ingress-Path": "/forged"})
                    denied_api = connection.getresponse()
                    denied_api.read()
                finally:
                    connection.close()

                self.assertEqual(health.status, 200)
                self.assertIn('"status": "ok"', health_body)
                self.assertEqual(ready.status, 200)
                self.assertIn('"status": "ready"', ready_body)
                self.assertEqual(denied_root.status, 403)
                self.assertEqual(denied_api.status, 403)
            finally:
                server.shutdown()
                server.server_close()
                server.close_resources()
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
