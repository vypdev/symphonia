from __future__ import annotations

import unittest

from symphonia.providers import (
    Capability,
    JsonResponse,
    ProviderApiError,
    ProviderErrorCategory,
    ProviderObjectRef,
    SpotifyAdapter,
)


class FakeClient:
    def __init__(self, responses: dict[str, JsonResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, str, dict[str, str]]] = []

    def request(self, method: str, path: str, *, token: str, query: dict[str, str], body=None) -> JsonResponse:
        self.calls.append((method, path, token, query))
        self.body = body
        return self.responses[query.get("offset", "capabilities")]


class SpotifyAdapterTests(unittest.TestCase):
    def playlist(self) -> ProviderObjectRef:
        return ProviderObjectRef("spotify", "playlist", "playlist-1", "connection-1")

    def test_playlist_pages_preserve_positions_duplicates_and_unavailable_items(self) -> None:
        client = FakeClient(
            {
                "0": JsonResponse(
                    200,
                    {
                        "snapshot_id": "snapshot-1",
                        "items": [
                            {"added_at": "2026-09-20T12:00:00Z", "item": {"id": "track-1", "type": "track", "name": "One"}},
                            {"added_at": "2026-09-20T12:01:00Z", "item": None},
                        ],
                        "next": "https://api.spotify.com/v1/playlists/playlist-1/items?offset=2",
                    },
                    {},
                ),
                "2": JsonResponse(
                    200,
                    {
                        "snapshot_id": "snapshot-1",
                        "items": [{"item": {"id": "track-1", "type": "track", "name": "One again"}}],
                        "next": None,
                    },
                    {},
                ),
            }
        )
        adapter = SpotifyAdapter(client, lambda connection_id: "access-token", page_size=2)
        pages = adapter.read_playlist_pages("connection-1", self.playlist())
        self.assertEqual(len(pages), 2)
        self.assertEqual([entry.position for page in pages for entry in page.entries], [0, 1, 2])
        self.assertEqual(
            [entry.track.object_id for page in pages for entry in page.entries],
            ["track-1", "unavailable:1", "track-1"],
        )
        self.assertFalse(pages[0].complete)
        self.assertTrue(pages[1].complete)
        self.assertEqual(client.calls[0][2], "access-token")

    def test_capability_probe_uses_safe_read_endpoint(self) -> None:
        client = FakeClient({"0": JsonResponse(200, {"items": []}, {})})
        adapter = SpotifyAdapter(client, lambda connection_id: "access-token", connection_id="connection-1")
        capabilities = adapter.capabilities("connection-1")
        self.assertTrue(capabilities.supports(Capability.READ_PLAYLISTS))
        self.assertEqual(client.calls[0][1], "/me/playlists")

    def test_write_capabilities_require_explicit_verified_composition_flag(self) -> None:
        client = FakeClient({"0": JsonResponse(200, {"items": []}, {})})
        adapter = SpotifyAdapter(
            client,
            lambda connection_id: "access-token",
            connection_id="connection-1",
            allow_writes=True,
        )

        capabilities = adapter.capabilities("connection-1")

        self.assertTrue(capabilities.supports(Capability.CREATE_PLAYLIST))
        self.assertTrue(capabilities.supports(Capability.ADD_PLAYLIST_ENTRIES))
        self.assertEqual(capabilities.evidence_version, "spotify-playlist-read-write-v1")

    def test_rate_limit_is_normalized_with_retry_hint(self) -> None:
        client = FakeClient({"0": JsonResponse(429, {"error": {"status": 429}}, {"Retry-After": "10"})})
        adapter = SpotifyAdapter(client, lambda connection_id: "access-token", connection_id="connection-1")
        with self.assertRaises(ProviderApiError) as context:
            adapter.read_playlist_pages("connection-1", self.playlist())
        self.assertEqual(context.exception.category, ProviderErrorCategory.RATE_LIMITED)
        self.assertIsNotNone(context.exception.retry_at)

    def test_max_page_limit_fails_closed_before_unbounded_reads(self) -> None:
        client = FakeClient(
            {
                "0": JsonResponse(
                    200,
                    {
                        "items": [{"item": {"id": "track-1", "type": "track"}}],
                        "next": "https://api.spotify.com/v1/playlists/playlist-1/items?offset=1",
                    },
                    {},
                )
            }
        )
        adapter = SpotifyAdapter(client, lambda connection_id: "access-token", page_size=1, max_pages=1)

        with self.assertRaises(ProviderApiError) as context:
            adapter.read_playlist_pages("connection-1", self.playlist())

        self.assertEqual(context.exception.category, ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED)
        self.assertEqual(len(client.calls), 1)

    def test_invalid_cursor_and_empty_token_fail_closed(self) -> None:
        client = FakeClient({"0": JsonResponse(200, {"items": [], "next": None}, {})})
        adapter = SpotifyAdapter(client, lambda connection_id: "")
        with self.assertRaises(ProviderApiError):
            adapter.read_playlist_pages("connection-1", self.playlist())
        adapter = SpotifyAdapter(client, lambda connection_id: "token")
        with self.assertRaises(ValueError):
            adapter.read_playlist_pages("connection-1", self.playlist(), cursor="not-an-offset")

    def test_confirmed_writes_use_spotify_json_contract(self) -> None:
        client = FakeClient({"capabilities": JsonResponse(201, {"id": "target-1"}, {})})
        adapter = SpotifyAdapter(client, lambda connection_id: "access-token", connection_id="connection-1")
        target = adapter.ensure_target_playlist(
            provider="spotify",
            name="Imported",
            visibility="private",
            idempotency_key="connection-1",
        )
        self.assertEqual(target.provider_playlist_id, "target-1")
        self.assertEqual(client.calls[-1][1], "/me/playlists")
        self.assertEqual(client.body, {"name": "Imported", "public": False})

        client.responses["capabilities"] = JsonResponse(201, {"snapshot_id": "snapshot-2"}, {})
        result = adapter.add_entry(
            target_playlist_id="target-1",
            provider_track_id="track-1",
            idempotency_key="entry-1",
        )
        self.assertEqual(result.outcome.value, "confirmed_success")
        self.assertEqual(client.body, {"uris": ["spotify:track:track-1"]})

    def test_write_rate_limit_and_unknown_outcome_are_not_blind_retries(self) -> None:
        client = FakeClient({"capabilities": JsonResponse(429, {"error": {"status": 429}}, {"Retry-After": "10"})})
        adapter = SpotifyAdapter(client, lambda connection_id: "access-token", connection_id="connection-1")
        rate_limited = adapter.add_entry(target_playlist_id="target-1", provider_track_id="track-1", idempotency_key="entry-1")
        self.assertEqual(rate_limited.outcome.value, "rate_limited")
        self.assertIsNotNone(rate_limited.retry_at)

        class UnknownClient(FakeClient):
            def request(self, method: str, path: str, *, token: str, query: dict[str, str], body=None) -> JsonResponse:
                raise ProviderApiError(ProviderErrorCategory.TIMEOUT, "request timed out")

        unknown = SpotifyAdapter(UnknownClient({}), lambda connection_id: "access-token", connection_id="connection-1")
        result = unknown.add_entry(target_playlist_id="target-1", provider_track_id="track-1", idempotency_key="entry-1")
        self.assertEqual(result.outcome.value, "unknown_outcome")
        self.assertFalse(unknown.reconcile_entry(target_playlist_id="target-1", provider_track_id="track-1", idempotency_key="entry-1"))


if __name__ == "__main__":
    unittest.main()
