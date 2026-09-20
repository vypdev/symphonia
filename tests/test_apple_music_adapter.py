from __future__ import annotations

import unittest

from symphonia.providers import (
    AppleJsonResponse,
    AppleMusicAdapter,
    Capability,
    MediaKind,
    ProviderApiError,
    ProviderErrorCategory,
    ProviderObjectRef,
)


class FakeAppleClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str, dict[str, str]]] = []

    def request(
        self,
        method: str,
        path: str,
        *,
        developer_token: str,
        user_token: str,
        query: dict[str, str],
    ) -> AppleJsonResponse:
        self.calls.append((method, path, developer_token, user_token, query))
        if path == "/me/library/playlists":
            return AppleJsonResponse(200, {"data": []}, {})
        if query["offset"] == "0":
            return AppleJsonResponse(
                200,
                {
                    "data": [
                        {"id": "library-song-1", "type": "library-songs", "attributes": {"name": "One"}},
                        {"type": "library-songs", "attributes": {"name": "Unavailable"}},
                    ],
                    "next": "https://api.music.apple.com/v1/me/library/playlists/playlist-1/tracks?offset=2",
                },
                {},
            )
        return AppleJsonResponse(
            200,
            {"data": [{"id": "catalog-song-2", "type": "songs", "attributes": {"name": "Two"}}]},
            {},
        )


class AppleMusicAdapterTests(unittest.TestCase):
    def playlist(self) -> ProviderObjectRef:
        return ProviderObjectRef("apple_music", "library-playlists", "playlist-1", "apple-connection-1")

    def test_library_playlist_pages_preserve_library_and_catalog_ids(self) -> None:
        client = FakeAppleClient()
        adapter = AppleMusicAdapter(client, lambda connection_id: ("developer-token", "user-token"), page_size=2)

        pages = adapter.read_playlist_pages("apple-connection-1", self.playlist())

        self.assertEqual(len(pages), 2)
        entries = [entry for page in pages for entry in page.entries]
        self.assertEqual([entry.position for entry in entries], [0, 1, 2])
        self.assertEqual(entries[0].media_kind, MediaKind.TRACK)
        self.assertEqual(entries[0].track.object_type, "library-songs")
        self.assertEqual(entries[0].track.object_id, "library-song-1")
        self.assertFalse(entries[1].available)
        self.assertEqual(entries[1].track.object_id, "unavailable:1")
        self.assertEqual(entries[2].track.object_type, "songs")
        self.assertEqual(client.calls[0][2:4], ("developer-token", "user-token"))

    def test_capability_probe_uses_user_library_endpoint(self) -> None:
        client = FakeAppleClient()
        adapter = AppleMusicAdapter(client, lambda connection_id: ("developer-token", "user-token"))

        capabilities = adapter.capabilities("apple-connection-1")

        self.assertTrue(capabilities.supports(Capability.READ_PLAYLISTS))
        self.assertEqual(client.calls[0][1], "/me/library/playlists")

    def test_missing_developer_or_user_token_fails_closed(self) -> None:
        adapter = AppleMusicAdapter(FakeAppleClient(), lambda connection_id: ("", "user-token"))

        with self.assertRaises(ProviderApiError) as context:
            adapter.read_playlist_pages("apple-connection-1", self.playlist())

        self.assertEqual(context.exception.category, ProviderErrorCategory.AUTHENTICATION_REQUIRED)

    def test_repeated_offset_is_a_provider_contract_failure(self) -> None:
        class LoopingClient(FakeAppleClient):
            def request(self, method, path, *, developer_token, user_token, query):
                self.calls.append((method, path, developer_token, user_token, query))
                return AppleJsonResponse(
                    200,
                    {
                        "data": [{"id": "song-1", "type": "songs", "attributes": {"name": "One"}}],
                        "next": "https://api.music.apple.com/v1/me/library/playlists/playlist-1/tracks?offset=0",
                    },
                    {},
                )

        with self.assertRaises(ProviderApiError) as context:
            AppleMusicAdapter(
                LoopingClient(), lambda connection_id: ("developer-token", "user-token"), page_size=1
            ).read_playlist_pages("apple-connection-1", self.playlist())

        self.assertEqual(context.exception.category, ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED)


if __name__ == "__main__":
    unittest.main()
