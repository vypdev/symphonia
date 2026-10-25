"""Authenticated provider requests never follow a server-directed redirect."""

from urllib.request import HTTPRedirectHandler, Request, build_opener


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_authenticated(request: Request, *, timeout: float):
    return build_opener(_RejectRedirects()).open(request, timeout=timeout)
