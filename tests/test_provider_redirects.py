"""Real loopback redirects must not cause a second authenticated request."""

from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import unittest

from symphonia.providers.apple_music import UrllibAppleMusicClient
from symphonia.providers.http_json import UrllibJsonClient


class ProviderRedirectTests(unittest.TestCase):
    def test_authenticated_transports_refuse_same_and_cross_origin_redirects(self) -> None:
        sink_requests = []
        source_requests = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.do_GET()

            def do_GET(self):
                if self.path == "/sink":
                    sink_requests.append(dict(self.headers))
                    self.send_response(200)
                    body = b'{}'
                else:
                    source_requests.append(dict(self.headers))
                    _, status, origin = self.path.split("/")
                    port = source.server_port if origin == "same" else target.server_port
                    self.send_response(int(status))
                    self.send_header("Location", f"http://127.0.0.1:{port}/sink")
                    body = b'{}'
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        with ExitStack() as stack:
            target = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            source = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            for server in (target, source):
                thread = Thread(target=lambda server=server: server.serve_forever(poll_interval=0.01), daemon=True)
                thread.start()
                stack.callback(server.server_close)
                stack.callback(thread.join, 2)
                stack.callback(server.shutdown)
            base_url = f"http://127.0.0.1:{source.server_port}"
            common = UrllibJsonClient(base_url=base_url)
            apple = UrllibAppleMusicClient(base_url=base_url)
            for status in (301, 302, 303, 307, 308):
                for origin in ("same", "cross"):
                    path = f"/{status}/{origin}"
                    for kind in ("common-get", "common-post", "apple-get"):
                        with self.subTest(status=status, origin=origin, kind=kind):
                            if kind == "apple-get":
                                response = apple.request("GET", path, developer_token="fixture-bearer", user_token="fixture-user", query={})
                                self.assertEqual(source_requests[-1]["Music-User-Token"], "fixture-user")
                            else:
                                response = common.request("POST" if kind == "common-post" else "GET", path,
                                                          token="fixture-bearer", query={}, body={} if kind == "common-post" else None)
                            self.assertEqual(source_requests[-1]["Authorization"], "Bearer fixture-bearer")
                            self.assertEqual(response.status, status)
                            self.assertEqual(sink_requests, [])
            self.assertEqual(len(source_requests), 30)
