from .client import InstagramClient
from .cookies import CookieClient
from .exceptions import *


def get_client(cookie_file: str | None = None, proxy: str | None = None) -> InstagramClient:
    if cookie_file:
        return CookieClient(cookie_file, proxy=proxy)

    try:
        from .credentials import CredentialsClient

        return CredentialsClient(proxy=proxy)
    except ImportError:
        raise MissingDependencyError("instagrapi is required for username/password authentication")

__all__ = ["get_client", "InstagramClient", "AuthError", "InstagramError", "MissingDependencyError", "UserNotFoundError", "UserNotLiveError"]