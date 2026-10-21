from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from symphonia.providers import AppleMusicAdapter, JsonResponse, SpotifyAdapter, YouTubeDataAdapter
from symphonia.providers.errors import ProviderApiError, ProviderErrorCategory
from symphonia.providers.retry_after import parse_retry_after


NOW = datetime(2026, 10, 21, 7, 26, tzinfo=timezone.utc)
DEADLINE = NOW + timedelta(minutes=2)


class RetryAfterTests(unittest.TestCase):
    def test_standard_seconds_and_http_date_forms_are_aware_instants(self) -> None:
        for value, expected in (("0", NOW), ("120", DEADLINE), (" 120 ", DEADLINE),
                                ("Wed, 21 Oct 2026 07:28:00 GMT", DEADLINE),
                                ("Wednesday, 21-Oct-26 07:28:00 GMT", DEADLINE),
                                ("Wed Oct 21 07:28:00 2026", DEADLINE),
                                ("Wed, 21 Oct 2026 06:26:00 GMT", NOW - timedelta(hours=1))):
            with self.subTest(value=value):
                self.assertEqual(parse_retry_after(value, now=NOW), expected)
        with self.assertRaises(ValueError):
            parse_retry_after("120", now=NOW.replace(tzinfo=None))

    def test_invalid_or_unrepresentable_headers_use_the_bounded_fallback(self) -> None:
        for value in (None, "", "  ", "invalid", "-1", "1.5", "١٢٠", "9" * 5000):
            with self.subTest(value=str(value)[:20]):
                self.assertIsNone(parse_retry_after(value, now=NOW))

    def test_all_three_adapters_retain_seconds_and_http_date_deadlines(self) -> None:
        for value in ("120", "Wed, 21 Oct 2026 07:28:00 GMT"):
            client = SimpleNamespace(request=lambda *args, **kwargs: JsonResponse(429, {}, {"rEtRy-AfTeR": value}))
            adapters = (
                (SpotifyAdapter(client, lambda _: "fixture"), "symphonia.providers.spotify_error_mapping"),
                (AppleMusicAdapter(client, lambda _: ("developer", "user")), "symphonia.providers.apple_music"),
                (YouTubeDataAdapter(client, lambda _: "fixture"), "symphonia.providers.youtube"),
            )
            for adapter, module in adapters:
                with self.subTest(adapter=module, value=value), patch(module + ".datetime") as clock:
                    clock.now.return_value = NOW
                    with self.assertRaises(ProviderApiError) as raised:
                        adapter.capabilities("fixture")
                    self.assertEqual(raised.exception.category, ProviderErrorCategory.RATE_LIMITED)
                    self.assertEqual(raised.exception.retry_at, DEADLINE)
