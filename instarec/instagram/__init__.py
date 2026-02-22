from .cookies import CookieClient
from .exceptions import *

async def get_mpd(identifier: str, cookie_file: str | None = None, proxy: str | None = None) -> str:
    if cookie_file:
        client = CookieClient(cookie_file, proxy=proxy)
        return await client.get_mpd(identifier)
    
    try:
        from .credentials import CredentialsClient  # noqa: F401
        client = CredentialsClient(proxy=proxy)
        return client.get_mpd(identifier)
    except ImportError:
        raise MissingDependencyError("instagrapi is required for username/password authentication")

__all__ = ["get_mpd", "InstagramClient", "AuthError", "InstagramError", "MissingDependencyError", "UserNotFound", "UserNotLiveError"]