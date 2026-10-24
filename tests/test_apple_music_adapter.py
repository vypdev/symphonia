from __future__ import annotations

import unittest
from symphonia.domain import EntryClassification
from symphonia.providers.importing import collect_playlist_pages, to_playlist_snapshot

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
    def test_next_links_cannot_change_the_playlist_resource_or_origin(self) -> None:
        for link in ("https://other.test/v1/me/library/playlists/playlist-1/tracks?offset=2", "http://api.music.apple.com/v1/me/library/playlists/playlist-1/tracks?offset=2", "//api.music.apple.com/v1/me/library/playlists/playlist-1/tracks?offset=2", "/v1/me/library/playlists/other/tracks?offset=2", "/v1/me/library/playlists/playlist-1/tracks?offset=2#fragment", "tracks?offset=2"):
            with self.subTest(link=link):
                class ChangedResourceClient(FakeAppleClient):
                    def request(self, *args, **kwargs):
                        response = super().request(*args, **kwargs)
                        if "next" in response.payload:
                            response.payload["next"] = link
                        return response

                client = ChangedResourceClient()
                with self.assertRaises(ProviderApiError):
                    AppleMusicAdapter(client, lambda _: ("developer", "user"), page_size=2).read_playlist_pages("apple-connection-1", self.playlist())
                self.assertEqual(len(client.calls), 1)

    def test_relative_next_link_reads_every_page_without_following_untrusted_urls(self) -> None:
        class RelativeClient(FakeAppleClient):
            def request(self, *args, **kwargs):
                response = super().request(*args, **kwargs)
                if "next" in response.payload:
                    response.payload["next"] = "/v1/me/library/playlists/playlist-1/tracks?offset=2"
                return response

        client = RelativeClient()
        pages = AppleMusicAdapter(client, lambda _: ("developer", "user"), page_size=2).read_playlist_pages("apple-connection-1", self.playlist())
        self.assertEqual(len(pages), 2)
        self.assertEqual([call[1] for call in client.calls], ["/me/library/playlists/playlist-1/tracks"] * 2)

    def test_missing_data_is_not_a_complete_empty_playlist(self) -> None:
        from types import SimpleNamespace
        client = SimpleNamespace(request=lambda *args, **kwargs: AppleJsonResponse(200, {}, {}))
        with self.assertRaises(ProviderApiError) as raised:
            AppleMusicAdapter(client, lambda _: ("developer", "user")).read_playlist_pages("account", self.playlist())
        self.assertEqual(raised.exception.category, ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED)

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

    def test_mixed_playlist_preserves_media_kinds_and_unknown_resources(self) -> None:
        kinds = ["songs", "library-songs", "music-videos", "library-music-videos", "future-resource"]

        class MixedClient(FakeAppleClient):
            def request(self, method, path, *, developer_token, user_token, query):
                return AppleJsonResponse(200, {"data": [{"id": f"item-{i}", "type": kind} for i, kind in enumerate(kinds)]}, {})

        adapter = AppleMusicAdapter(MixedClient(), lambda _: ("developer", "user"))
        entries = adapter.read_playlist_pages("apple-connection-1", self.playlist())[0].entries
        self.assertEqual([entry.media_kind for entry in entries], [MediaKind.TRACK, MediaKind.TRACK, MediaKind.VIDEO, MediaKind.VIDEO, MediaKind.UNKNOWN])
        self.assertEqual([entry.track.object_type for entry in entries], kinds)
        self.assertEqual([entry.position for entry in entries], list(range(5)))
        self.assertEqual([entry.available for entry in entries], [True, True, True, True, False])
        self.assertEqual(entries[-1].track.object_id, "item-4")

    def test_unknown_or_missing_type_retains_identity_but_cannot_enter_matching(self) -> None:
        for raw_type in ("future-resource", None, "", {}, []):
            with self.subTest(resource_type=raw_type):
                class UnknownClient:
                    def request(self, *args, **kwargs):
                        return AppleJsonResponse(200, {"data": [{"id": "retained-id", "type": raw_type}]}, {})

                pages = AppleMusicAdapter(UnknownClient(), lambda _: ("developer", "user")).read_playlist_pages("account", self.playlist())
                entry = pages[0].entries[0]
                self.assertEqual(entry.track.object_id, "retained-id")
                self.assertEqual(entry.media_kind, MediaKind.UNKNOWN)
                self.assertFalse(entry.available)
                snapshot = to_playlist_snapshot(collect_playlist_pages(pages), "unknown-resource")
                self.assertEqual(snapshot.entries[0].classification, EntryClassification.UNAVAILABLE)

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

        for token_pair in ((None, "user-token"), ("developer-token",), ("developer-token", {})):
            adapter = AppleMusicAdapter(FakeAppleClient(), lambda connection_id, pair=token_pair: pair)  # type: ignore[arg-type]
            with self.subTest(token_pair=token_pair), self.assertRaises(ProviderApiError) as context:
                adapter.read_playlist_pages("apple-connection-1", self.playlist())
            self.assertEqual(context.exception.category, ProviderErrorCategory.AUTHENTICATION_REQUIRED)

    def test_malformed_next_link_fails_closed_without_fallback_pagination(self) -> None:
        class MalformedClient(FakeAppleClient):
            def request(self, method, path, *, developer_token, user_token, query):
                self.calls.append((method, path, developer_token, user_token, query))
                return AppleJsonResponse(
                    200,
                    {
                        "data": [{"id": "song-1", "type": "songs", "attributes": {"name": "One"}}],
                        "next": "https://api.music.apple.com/v1/me/library/playlists/playlist-1/tracks?offset=not-an-integer",
                    },
                    {},
                )

        with self.assertRaises(ProviderApiError) as context:
            AppleMusicAdapter(
                MalformedClient(), lambda connection_id: ("developer-token", "user-token")
            ).read_playlist_pages("apple-connection-1", self.playlist())
        self.assertEqual(context.exception.category, ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED)

    def test_forward_pagination_gap_is_rejected_before_a_second_read(self) -> None:
        class GapClient(FakeAppleClient):
            def request(self, *args, **kwargs):
                response = super().request(*args, **kwargs)
                response.payload["next"] = "https://api.music.apple.com/v1/me/library/playlists/playlist-1/tracks?offset=3"
                return response

        client = GapClient()
        with self.assertRaises(ProviderApiError) as context:
            AppleMusicAdapter(client, lambda _: ("developer", "user")).read_playlist_pages(
                "apple-connection-1", self.playlist(),
            )
        self.assertEqual(context.exception.category, ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED)
        self.assertEqual(len(client.calls), 1)

    def test_playlist_identifier_is_encoded_as_one_opaque_path_segment(self) -> None:
        client = FakeAppleClient()
        playlist = ProviderObjectRef("apple_music", "library-playlists", "a/b?c#d%", "apple-connection-1")
        AppleMusicAdapter(client, lambda _: ("developer", "user")).read_playlist_pages(
            "apple-connection-1", playlist, cursor="2",
        )
        self.assertEqual(client.calls[0][1], "/me/library/playlists/a%2Fb%3Fc%23d%25/tracks")

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

    def test_max_page_limit_fails_closed_before_unbounded_reads(self) -> None:
        with self.assertRaises(ProviderApiError) as context:
            AppleMusicAdapter(
                FakeAppleClient(), lambda connection_id: ("developer-token", "user-token"), max_pages=1
            ).read_playlist_pages("apple-connection-1", self.playlist())

        self.assertEqual(context.exception.category, ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED)

    def test_non_textual_cursor_is_rejected_before_provider_request(self) -> None:
        with self.assertRaises(ValueError):
            AppleMusicAdapter(
                FakeAppleClient(), lambda connection_id: ("developer-token", "user-token")
            ).read_playlist_pages("apple-connection-1", self.playlist(), cursor=True)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
