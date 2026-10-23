from io import BytesIO
import json
from unittest.mock import MagicMock, patch
import unittest
from urllib.error import HTTPError

from symphonia.providers import AppleMusicAdapter, ProviderApiError, ProviderErrorCategory
from symphonia.providers.apple_music import UrllibAppleMusicClient
from symphonia.providers.http_json import UrllibJsonClient


class ProviderHttpJsonTests(unittest.TestCase):
    def transports(self):
        for label in ("Spotify", "YouTube Data"):
            client = UrllibJsonClient(provider_label=label)
            yield label, "symphonia.providers.http_json.urlopen", lambda client=client: client.request(
                "GET", "/fixture", token="private-token", query={},
            )
        client = UrllibAppleMusicClient()
        yield "Apple Music", "symphonia.providers.apple_music.urlopen", lambda: client.request(
            "GET", "/fixture", developer_token="private-token", user_token="private-user", query={},
        )

    def test_malformed_successes_have_sanitized_contract_errors(self) -> None:
        bodies = (b'\xffprivate-body', b'{"token":"private-body"', b'[]', b'null', b'"private-body"', b'42')
        for label, target, request in self.transports():
            for body in bodies:
                with self.subTest(provider=label, body=body):
                    response = MagicMock(status=200, headers={})
                    response.read.return_value = body
                    response.__enter__.return_value = response
                    with patch(target, return_value=response), self.assertRaises(ProviderApiError) as raised:
                        request()
                    error = raised.exception
                    self.assertEqual(error.category, ProviderErrorCategory.PROVIDER_CONTRACT_CHANGED)
                    self.assertIn(label, str(error))
                    self.assertNotIn("private", str(error))
                    self.assertIsNone(error.__cause__)
                    response.__exit__.assert_called_once()

    def test_valid_empty_and_object_successes_remain_readable(self) -> None:
        for label, target, request in self.transports():
            for body, payload in ((b'', {}), (b'{"items":[]}', {"items": []})):
                with self.subTest(provider=label, body=body):
                    response = MagicMock(status=200, headers={})
                    response.read.return_value = body
                    response.__enter__.return_value = response
                    with patch(target, return_value=response):
                        result = request()
                    self.assertEqual(result.payload, payload)
                    self.assertEqual(result.status, 200)

    def test_apple_error_bodies_keep_http_classification_without_object_assumptions(self) -> None:
        categories = {401: ProviderErrorCategory.AUTHENTICATION_REQUIRED,
                      403: ProviderErrorCategory.PERMISSION_DENIED,
                      404: ProviderErrorCategory.NOT_FOUND,
                      429: ProviderErrorCategory.RATE_LIMITED,
                      500: ProviderErrorCategory.PROVIDER_UNAVAILABLE}
        bodies = [json.dumps(value).encode() for value in ([], None, "private-body", 42)]
        bodies += [b'\xffprivate-body', b'{"token":"private-body"']
        for status, category in categories.items():
            for body in bodies:
                with self.subTest(status=status, body=body):
                    failure = HTTPError("https://example.invalid", status, "private-body", {}, BytesIO(body))
                    adapter = AppleMusicAdapter(None, lambda _: ("private-token", "private-user"))
                    with patch("symphonia.providers.apple_music.urlopen", side_effect=failure):
                        with self.assertRaises(ProviderApiError) as raised:
                            adapter.capabilities("fixture")
                    self.assertEqual(raised.exception.category, category)
                    self.assertEqual(raised.exception.provider_code, str(status))
                    self.assertNotIn("private", str(raised.exception))
                    failure.close()
