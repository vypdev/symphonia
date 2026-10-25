from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from tools.ha_ingress_probe import lab_owner_id, probe, proxy_path


INGRESS_URL = "/api/hassio_ingress/synthetic_route"
SESSION = "synthetic_session"
USER_ID = "a" * 32


class IngressProbeTests(unittest.TestCase):
    def test_selects_only_fixed_routes_under_the_supervisor_prefix(self) -> None:
        self.assertEqual(proxy_path(INGRESS_URL, "health"), "/ingress/synthetic_route/health")
        self.assertEqual(proxy_path(INGRESS_URL + "/optional-entry", "ready"), "/ingress/synthetic_route/ready")
        self.assertEqual(proxy_path(INGRESS_URL, ""), "/ingress/synthetic_route/")
        self.assertEqual(proxy_path(INGRESS_URL, "api/dashboard"), "/ingress/synthetic_route/api/dashboard")
        self.assertEqual(proxy_path(INGRESS_URL, "assets/index-abc.js"), "/ingress/synthetic_route/assets/index-abc.js")

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
                self.assertEqual(json.loads(data), {"user_id": USER_ID})
                return 200, json.dumps({"data": {"session": SESSION}}).encode()
            if path == "/addons/local_symphonia/info":
                return 200, json.dumps({"data": {"state": "started", "ingress_url": INGRESS_URL}}).encode()
            if session is None:
                return 401, b"Unauthorized"
            if path.endswith("/health"):
                return 200, b'{"service":"symphonia","status":"ok"}'
            if path.endswith("/ready"):
                return 200, b'{"service":"symphonia","status":"ready"}'
            if path.endswith("/api/dashboard"):
                return 200, b'{"service":"symphonia","ready":true}'
            if path.endswith("/assets/index-abc.js"):
                return 200, b"console.log('fixture')"
            return 200, b'<html><script src="./assets/index-abc.js"></script></html>'

        result = probe(request, user_id=USER_ID)

        self.assertEqual(result["without_session"], 401)
        self.assertEqual(result["health"], 200)
        self.assertEqual(result["ready"], 200)
        self.assertEqual(result["root"], 200)
        self.assertEqual(result["dashboard"], 200)
        self.assertTrue(result["has_ui_asset"])
        self.assertEqual(result["asset"], 200)
        self.assertTrue(result["dashboard_ready"])
        self.assertNotIn(SESSION, json.dumps(result))
        self.assertNotIn("synthetic_route", json.dumps(result))
        self.assertNotIn(USER_ID, json.dumps(result))
        self.assertEqual(len(calls), 8)

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
            probe(request, user_id=USER_ID)

    def test_invalid_user_id_is_rejected_before_session_creation(self) -> None:
        for user_id in (None, "", "a" * 31, "a" * 33, "g" * 32, "a" * 31 + "\n", 42):
            with self.subTest(user_id=user_id), self.assertRaises(ValueError):
                request = Mock()
                probe(request, user_id=user_id)
            request.assert_not_called()

    def test_disposable_owner_selection_fails_closed(self) -> None:
        owner = {"id": USER_ID, "is_owner": True, "is_active": True}
        fixtures = [
            ({"data": {"users": [owner]}}, USER_ID),
            ({"data": {"users": [owner, {"id": "b" * 32, "is_owner": False}]}}, USER_ID),
            ({"data": {"users": []}}, None),
            ({"data": {"users": [owner, owner]}}, None),
            ({"data": {"users": [{**owner, "is_active": False}]}}, None),
            ({"data": {"users": [{**owner, "id": "invalid"}]}}, None),
            ({"data": {"users": None}}, None),
            ([], None),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "auth"
            for fixture, expected in fixtures:
                path.write_text(json.dumps(fixture), encoding="utf-8")
                with self.subTest(fixture=fixture):
                    if expected is None:
                        with self.assertRaises(ValueError):
                            lab_owner_id(path)
                    else:
                        self.assertEqual(lab_owner_id(path), expected)


if __name__ == "__main__":
    unittest.main()
