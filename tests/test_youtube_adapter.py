from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
