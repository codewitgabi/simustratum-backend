from urllib.parse import urlparse

from fastapi import Request

from api.v1.utils.config import config


def get_client_origin(request: Request) -> str:
    """
    Resolves the frontend's base URL for building links (e.g. a password reset
    link) without requiring the caller to pass it explicitly in the request body.

    Browsers attach an `Origin` header to fetch/XHR requests automatically, and a
    `Referer` header on plain navigations — either tells us where the request
    actually came from. (The User-Agent header only describes the browser/OS, not
    a URL, so it can't be used for this.) Falls back to a configured FRONTEND_URL,
    then to the API's own host, for non-browser callers that send neither header.
    """
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/")

    referer = request.headers.get("referer")
    if referer:
        parsed = urlparse(referer)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"

    if config.FRONTEND_URL:
        return config.FRONTEND_URL.rstrip("/")

    return str(request.base_url).rstrip("/")
