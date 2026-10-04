from __future__ import annotations

from datetime import datetime, timezone
import unittest

from symphonia.application.operational_dashboard import project_dashboard
from symphonia.runtime.dashboard_surface import dashboard_response
from symphonia.runtime.http import trusted_ingress_peer, ui_asset


NOW = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)


class OperationalDashboardTests(unittest.TestCase):
    def test_dashboard_adapter_returns_bounded_projection_and_fails_closed(self) -> None:
        expected_request = (NOW, 10, 1)

        class Diagnostics:
            def __init__(self, result: dict[str, object] | Exception) -> None:
                self.result = result

            def diagnostics(self, *, now: datetime, operation_limit: int, event_limit: int) -> dict[str, object]:
                if (now, operation_limit, event_limit) != expected_request:
                    raise AssertionError("unbounded diagnostics read")
                if isinstance(self.result, Exception):
                    raise self.result
                return self.result

        healthy = Diagnostics({"ready": True})
        status, payload = dashboard_response(healthy, now=NOW, version="0.1.0")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ready"])
        for resources in (None, Diagnostics({"ready": False}), Diagnostics(RuntimeError("secret"))):
            status, payload = dashboard_response(resources, now=NOW, version="0.1.0")
            self.assertEqual(status, 503)
            self.assertEqual(payload, {"service": "symphonia", "ready": False})

    def test_projection_uses_exact_allowlist_and_omits_secret_bearing_diagnostics(self) -> None:
        secret = "credential-canary-very-private"
        diagnostics = {
            "ready": True,
            "database_path": secret,
            "queue": {"total": 1, "eligible_count": 1, "states": {"queued": 1}, "secret": secret},
            "connections": {"total": 0, "expired_count": 0, "by_provider": {}},
            "projections": {"current_playlist_count": 0, "entry_count": 0, "unavailable_entry_count": 0},
            "resolutions": {"total": 0, "by_action": {}},
            "operations": [{"operation_id": "op-1", "operation_type": "copy", "state": "queued", "updated_at": "2026-10-04T12:00:00+00:00", "payload": secret, "events": [{"payload": secret}]}],
        }
        view = project_dashboard(diagnostics, now=NOW, version="0.1.0")
        self.assertEqual(set(view), {"service", "version", "ready", "generated_at", "queue", "connections", "library", "resolutions", "operations"})
        self.assertEqual(view["operations"], [{"id": "op-1", "type": "copy", "state": "queued", "updated_at": "2026-10-04T12:00:00+00:00"}])
        self.assertNotIn(secret, str(view))

    def test_unready_resources_return_no_partial_or_sensitive_facts(self) -> None:
        view = project_dashboard({"ready": False, "queue": {"total": 5}}, now=NOW, version="0.1.0")
        self.assertEqual(view, {"service": "symphonia", "ready": False})

    def test_operation_count_and_labels_are_bounded(self) -> None:
        diagnostics = {"ready": True, "operations": [{"operation_id": "a" * 500, "state": "queued\nsecret"}] * 20}
        view = project_dashboard(diagnostics, now=NOW, version="0.1.0")
        self.assertEqual(len(view["operations"]), 10)
        self.assertEqual(len(view["operations"][0]["id"]), 64)
        self.assertNotIn("\n", view["operations"][0]["state"])

    def test_only_supervisor_peer_is_trusted(self) -> None:
        self.assertTrue(trusted_ingress_peer("172.30.32.2"))
        for address in ("127.0.0.1", "172.30.32.1", "::1", "172.30.32.2.example"):
            self.assertFalse(trusted_ingress_peer(address))

    def test_static_assets_are_allowlisted_and_relative(self) -> None:
        root = ui_asset("/")
        self.assertIsNotNone(root)
        assert root is not None
        self.assertEqual(root[0], "text/html; charset=utf-8")
        self.assertIn(b'./assets/', root[1])
        self.assertNotIn(b'src="/assets/', root[1])
        for path in ("/assets/../index.html", "/assets/%2e%2e/index.html", "/assets/x.js/other", "/admin"):
            self.assertIsNone(ui_asset(path))


if __name__ == "__main__":
    unittest.main()
