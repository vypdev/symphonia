from __future__ import annotations

import unittest
from unittest.mock import patch
from urllib.error import URLError

from symphonia.providers import (
    Capability,
    JsonResponse,
    MediaKind,
    ProviderObjectRef,
    ProviderApiError,
    ProviderErrorCategory,
    YouTubeDataAdapter,
)


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def request(self, method: str, path: str, *, token: str, query: dict[str, str], body=None) -> JsonResponse:
        self.calls.append((method, path, token, query))
        if path == "/channels":
            return JsonResponse(200, {"items": [{"id": "channel-1"}]}, {})
        if query.get("pageToken") is None:
            return JsonResponse(
                200,
                {
                    "etag": "etag-1",
                    "items": [
                        {
                            "id": "playlist-item-1",
                            "snippet": {
                                "title": "Song video",
                                "publishedAt": "2026-09-20T12:00:00Z",
                                "resourceId": {"kind": "youtube#video", "videoId": "video-1"},
                            },
                        },
                        {
                            "id": "playlist-item-2",
                            "snippet": {"title": "Deleted video", "resourceId": {"kind": "youtube#video"}},
                        },
                    ],
                    "nextPageToken": "page-2",
                },
                {},
            )
        return JsonResponse(
            200,
            {
                "etag": "etag-2",
                "items": [
                    {
                        "id": "playlist-item-3",
                        "contentDetails": {"videoId": "video-2"},
                        "snippet": {"title": "Second video", "resourceId": {}},
                    }
                ],
            },
            {},
        )


class YouTubeDataAdapterTests(unittest.TestCase):
    def test_standalone_continuation_preserves_absolute_provider_positions(self) -> None:
        from symphonia.providers.importing import collect_playlist_pages

        class ContinuationClient:
            def __init__(self):
                self.tokens = []

            def request(self, method, path, *, token, query, body=None):
                self.tokens.append(query["pageToken"])
                first = query["pageToken"] == "opaque-a"
                positions = (50, 51) if first else (52,)
                return JsonResponse(200, {"items": [{"id": f"occ-{p}", "snippet": {
                    "position": p, "resourceId": {"videoId": f"video-{p}"}}} for p in positions],
                    **({"nextPageToken": "opaque-b"} if first else {})}, {})

        client = ContinuationClient()
        playlist = ProviderObjectRef("youtube_data", "playlist", "playlist", "account")
        pages = YouTubeDataAdapter(client, lambda _: "fixture").read_playlist_pages("account", playlist, cursor="opaque-a")
        self.assertEqual(client.tokens, ["opaque-a", "opaque-b"])
        self.assertEqual([e.position for p in pages for e in p.entries], [50, 51, 52])
        self.assertFalse(collect_playlist_pages(pages).complete)

    def test_resumed_pages_with_missing_or_inconsistent_positions_fail_closed(self) -> None:
        from types import SimpleNamespace
        playlist = ProviderObjectRef("youtube_data", "playlist", "playlist", "account")
        snippets = [{}] + [{"position": value} for value in (None, False, -1, "50", [], {})]
        for snippet in snippets:
            with self.subTest(snippet=snippet):
                client = SimpleNamespace(request=lambda *args, **kwargs: JsonResponse(200, {
                    "items": [{"snippet": snippet}]}, {}))
                with self.assertRaises(ProviderApiError):
                    YouTubeDataAdapter(client, lambda _: "fixture").read_playlist_pages("account", playlist, cursor="opaque")
        client = SimpleNamespace(request=lambda *args, **kwargs: JsonResponse(200, {
            "items": [{"snippet": {"position": 50}}, {"snippet": {"position": 52}}]}, {}))
        with self.assertRaises(ProviderApiError):
            YouTubeDataAdapter(client, lambda _: "fixture").read_playlist_pages("account", playlist, cursor="opaque")

    def test_quota_403_reasons_are_rate_limits_but_permissions_remain_distinct(self) -> None:
        from types import SimpleNamespace
        for reason in ("quotaExceeded", "dailyLimitExceeded", "userRateLimitExceeded", "rateLimitExceeded", "servingLimitExceeded",
                       "insufficientPermissions", [], {}):
            with self.subTest(reason=reason):
                response = JsonResponse(403, {"error": {"errors": [{"reason": reason}]}}, {"Retry-After": "120"})
                client = SimpleNamespace(request=lambda *args, **kwargs: response)
                with self.assertRaises(ProviderApiError) as raised:
                    YouTubeDataAdapter(client, lambda _: "fixture").capabilities("account")
                limited = isinstance(reason, str) and reason != "insufficientPermissions"
                self.assertEqual(raised.exception.category, ProviderErrorCategory.RATE_LIMITED if limited else ProviderErrorCategory.PERMISSION_DENIED)
                self.assertEqual(raised.exception.retry_at is not None, limited)

    def test_missing_items_requires_explicit_first_page_empty_evidence(self) -> None:
        from types import SimpleNamespace
        playlist = ProviderObjectRef("youtube_data", "playlist", "playlist", "account")
        kind = {"kind": "youtube#playlistItemListResponse"}
        invalid = ({}, {"pageInfo": {"totalResults": 0}},
                   {**kind, "pageInfo": {"totalResults": 1}}, {**kind, "pageInfo": {"totalResults": False}},
                   {**kind, "pageInfo": {"totalResults": "0"}},
                   {**kind, "pageInfo": {"totalResults": 0}, "nextPageToken": "next"},
                   {**kind, "pageInfo": {"totalResults": 0}, "prevPageToken": "previous"},
                   {**kind, "pageInfo": {"totalResults": 0}, "items": None},
                   {**kind, "pageInfo": {"totalResults": 0}, "items": {}})
        for payload in invalid:
            with self.subTest(payload=payload):
                client = SimpleNamespace(request=lambda *args, **kwargs: JsonResponse(200, payload, {}))
                with self.assertRaises(ProviderApiError) as raised:
                    YouTubeDataAdapter(client, lambda _: "fixture").read_playlist_pages("account", playlist)
                self.assertEqual(raised.exception.category, ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED)
        client = SimpleNamespace(request=lambda *args, **kwargs: JsonResponse(200, {
            "kind": "youtube#playlistItemListResponse", "pageInfo": {"totalResults": 0},
        }, {}))
        adapter = YouTubeDataAdapter(client, lambda _: "fixture")
        page = adapter.read_playlist_pages("account", playlist)[0]
        self.assertTrue(page.complete)
        self.assertEqual(page.entries, ())
        with self.assertRaises(ProviderApiError):
            adapter.read_playlist_pages("account", playlist, cursor="resumed")

    def test_default_transport_reports_youtube_network_failures_without_secrets(self) -> None:
        adapter = YouTubeDataAdapter(None, lambda connection_id: "token=private-value")
        for failure, category in (
            (TimeoutError("private-value"), ProviderErrorCategory.TIMEOUT),
            (URLError("private-value"), ProviderErrorCategory.NETWORK_ERROR),
        ):
            with self.subTest(category=category), patch(
                "symphonia.providers.http_json.urlopen", side_effect=failure
            ):
                with self.assertRaises(ProviderApiError) as raised:
                    adapter.capabilities("google-connection-1")
                self.assertEqual(raised.exception.category, category)
                self.assertIn("YouTube Data", str(raised.exception))
                self.assertNotIn("Spotify", str(raised.exception))
                self.assertNotIn("private-value", str(raised.exception))

    def test_official_video_playlist_pages_preserve_unavailable_items(self) -> None:
        client = FakeClient()
        adapter = YouTubeDataAdapter(client, lambda connection_id: "access-token", page_size=2, api_key="public-key")
        playlist = ProviderObjectRef("youtube_data", "playlist", "playlist-1", "google-connection-1")
        pages = adapter.read_playlist_pages("google-connection-1", playlist)
        self.assertEqual(len(pages), 2)
        entries = [entry for page in pages for entry in page.entries]
        self.assertEqual([entry.position for entry in entries], [0, 1, 2])
        self.assertEqual(entries[0].media_kind, MediaKind.VIDEO)
        self.assertEqual(entries[0].track.object_id, "video-1")
        self.assertFalse(entries[1].available)
        self.assertEqual(entries[1].track.object_id, "unavailable:1")
        self.assertEqual(client.calls[0][3]["key"], "public-key")

    def test_capability_probe_is_separate_from_playlist_read(self) -> None:
        adapter = YouTubeDataAdapter(FakeClient(), lambda connection_id: "access-token")
        capabilities = adapter.capabilities("google-connection-1")
        self.assertEqual(capabilities.enabled, frozenset({Capability.READ_PLAYLISTS}))

    def test_repeated_page_token_is_a_provider_contract_failure(self) -> None:
        class LoopingClient(FakeClient):
            def request(self, method: str, path: str, *, token: str, query: dict[str, str], body=None) -> JsonResponse:
                self.calls.append((method, path, token, query))
                return JsonResponse(
                    200,
                    {
                        "items": [
                            {
                                "id": "playlist-item-1",
                                "snippet": {"resourceId": {"videoId": "video-1"}},
                            }
                        ],
                        "nextPageToken": "same-token",
                    },
                    {},
                )

        playlist = ProviderObjectRef("youtube_data", "playlist", "playlist-1", "connection-1")
        with self.assertRaises(ProviderApiError) as context:
            YouTubeDataAdapter(LoopingClient(), lambda connection_id: "access-token").read_playlist_pages(
                "connection-1", playlist
            )
        self.assertEqual(context.exception.category, ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED)

    def test_non_textual_page_token_is_a_provider_contract_failure(self) -> None:
        class MalformedClient(FakeClient):
            def request(self, method: str, path: str, *, token: str, query: dict[str, str], body=None) -> JsonResponse:
                self.calls.append((method, path, token, query))
                if path == "/channels":
                    return JsonResponse(200, {"items": [{"id": "channel-1"}]}, {})
                return JsonResponse(200, {"items": [], "nextPageToken": {"unexpected": "object"}}, {})

        playlist = ProviderObjectRef("youtube_data", "playlist", "playlist-1", "connection-1")
        with self.assertRaises(ProviderApiError) as context:
            YouTubeDataAdapter(MalformedClient(), lambda connection_id: "access-token").read_playlist_pages(
                "connection-1", playlist
            )
        self.assertEqual(context.exception.category, ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED)

    def test_non_textual_access_token_fails_as_authentication_required(self) -> None:
        playlist = ProviderObjectRef("youtube_data", "playlist", "playlist-1", "connection-1")
        with self.assertRaises(ProviderApiError) as context:
            YouTubeDataAdapter(FakeClient(), lambda connection_id: None).read_playlist_pages(  # type: ignore[arg-type]
                "connection-1", playlist
            )
        self.assertEqual(context.exception.category, ProviderErrorCategory.AUTHENTICATION_REQUIRED)

    def test_max_page_limit_fails_closed_before_unbounded_reads(self) -> None:
        playlist = ProviderObjectRef("youtube_data", "playlist", "playlist-1", "connection-1")
        adapter = YouTubeDataAdapter(FakeClient(), lambda connection_id: "access-token", max_pages=1)

        with self.assertRaises(ProviderApiError) as context:
            adapter.read_playlist_pages("connection-1", playlist)

        self.assertEqual(context.exception.category, ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED)

    def test_non_textual_cursor_is_rejected_before_provider_request(self) -> None:
        playlist = ProviderObjectRef("youtube_data", "playlist", "playlist-1", "connection-1")
        with self.assertRaises(ValueError):
            YouTubeDataAdapter(FakeClient(), lambda connection_id: "access-token").read_playlist_pages(
                "connection-1", playlist, cursor={"unexpected": "object"}  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
