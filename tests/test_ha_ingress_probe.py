from __future__ import annotations

import json
import unittest

from tools.ha_ingress_probe import probe, proxy_path


INGRESS_URL = "/api/hassio_ingress/synthetic_route"
SESSION = "synthetic_session"


class IngressProbeTests(unittest.TestCase):
    def test_selects_only_fixed_routes_under_the_supervisor_prefix(self) -> None:
        self.assertEqual(proxy_path(INGRESS_URL, "health"), "/ingress/synthetic_route/health")
        self.assertEqual(proxy_path(INGRESS_URL + "/optional-entry", "ready"), "/ingress/synthetic_route/ready")
        self.assertEqual(proxy_path(INGRESS_URL, ""), "/ingress/synthetic_route/")

    def test_rejects_external_malformed_or_unbounded_routes(self) -> None:
        for url in (
            "https://example.org/api/hassio_ingress/synthetic_route",
            "//example.org/api/hassio_ingress/synthetic_route",
            "/api/hassio_ingress/",
            "/api/hassio_ingress/unsafe%2Froute",
            "/api/hassio_ingress/synthetic_route?secret=1",
            "/other/synthetic_route",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                proxy_path(url, "health")
        with self.assertRaises(ValueError):
            proxy_path(INGRESS_URL, "../../outside")

    def test_probe_verifies_proxy_and_session_without_returning_secrets(self) -> None:
        calls: list[tuple[str, str, str | None]] = []

        def request(path: str, method: str, data: bytes | None, session: str | None) -> tuple[int, bytes]:
            calls.append((path, method, session))
            if path == "/ingress/session":
                self.assertEqual(data, b"{}")
                return 200, json.dumps({"data": {"session": SESSION}}).encode()
            if path == "/addons/local_symphonia/info":
                return 200, json.dumps({"data": {"state": "started", "ingress_url": INGRESS_URL}}).encode()
            if session is None:
                return 401, b"Unauthorized"
            if path.endswith("/health"):
                return 200, b'{"service":"symphonia","status":"ok"}'
            if path.endswith("/ready"):
                return 200, b'{"service":"symphonia","status":"ready"}'
            return 404, b'{"error":"not_found"}'

        result = probe(request)

        self.assertEqual(result["without_session"], 401)
        self.assertEqual(result["health"], 200)
        self.assertEqual(result["ready"], 200)
        self.assertEqual(result["root"], 404)
        self.assertNotIn(SESSION, json.dumps(result))
        self.assertNotIn("synthetic_route", json.dumps(result))
        self.assertEqual(len(calls), 6)

    def test_probe_fails_if_proxy_allows_a_request_without_session(self) -> None:
        def request(path: str, method: str, data: bytes | None, session: str | None) -> tuple[int, bytes]:
            if path == "/ingress/session":
                return 200, b'{"data":{"session":"synthetic_session"}}'
            if path == "/addons/local_symphonia/info":
                return 200, b'{"data":{"state":"started","ingress_url":"/api/hassio_ingress/synthetic_route"}}'
            if path.endswith("/health"):
                return 200, b'{"service":"symphonia","status":"ok"}'
            if path.endswith("/ready"):
                return 200, b'{"service":"symphonia","status":"ready"}'
            return 404, b'{"error":"not_found"}'

        with self.assertRaisesRegex(RuntimeError, "Ingress smoke failed"):
            probe(request)


if __name__ == "__main__":
    unittest.main()
