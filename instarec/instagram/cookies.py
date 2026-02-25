from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp_socks import ProxyConnector

from .. import log
from .client import InstagramClient
from .exceptions import AuthError, InstagramError, UserNotFoundError

BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "x-ig-app-id": "936619743392459",
}

USER_API_URL = "https://www.instagram.com/web/search/topsearch/?query={username}"
LIVE_API_URL = "https://www.instagram.com/api/v1/live/web_info/?target_user_id={user_id}"
STORY_FEED_API_URL = "https://www.instagram.com/api/v1/feed/user/{user_id}/story/"


class CookieClient(InstagramClient):
    def __init__(self, cookie_file: str, proxy: str | None = None):
        super().__init__(proxy)
        self.session: aiohttp.ClientSession | None = None
        self.cookies = self._load_cookies(cookie_file)
        self.headers = dict(BASE_HEADERS)
        if csrf_token := self.cookies.get("csrftoken"):
            self.headers["x-csrftoken"] = csrf_token
        else:
            log.API.warning("No 'csrftoken' found in cookies. API calls may fail.")

    def _load_cookies(self, cookie_file: str):
        if not Path(cookie_file).exists():
            raise FileNotFoundError(f"Cookie file not found: {cookie_file}")

        log.API.debug(f"Loading cookies from: {cookie_file}")
        jar = MozillaCookieJar(cookie_file)
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
            log.API.debug("Cookie session built successfully.")
            return {cookie.name: cookie.value for cookie in jar}
        except Exception as e:
            raise AuthError(f"Could not parse cookie file: {e}") from e

    async def __aenter__(self):
        connector = None
        if self.proxy:
            connector = ProxyConnector.from_url(self.proxy)
            log.API.debug(f"Cookie session proxy set: {self.proxy}")

        self.session = aiohttp.ClientSession(connector=connector, headers=self.headers, cookies=self.cookies)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            self.session = None

    async def _get(self, url: str) -> dict:
        log.API.debug(f"Cookie GET: {url}")
        try:
            async with self.session.get(url, timeout=10) as resp:
                if resp.status in (401, 403):
                    raise AuthError(
                        f"Authentication failed (Status {resp.status}). Your cookies are likely expired or invalid."
                    )
                if resp.status == 404:
                    raise UserNotFoundError(f"Instagram returned 404 for {url}")
                if resp.status == 429:
                    raise InstagramError(f"Too many requests (429) for {url}")

                content_type = resp.headers.get("Content-Type", "")
                text = await resp.text()

                if "text/html" in content_type or text.lstrip().startswith("<!DOCTYPE"):
                    log.API.debug(f"Raw response (status {resp.status}): {text[:500]!r}")
                    raise AuthError("Instagram redirected to the login page. Your cookies are invalid.")

                try:
                    return await resp.json()
                except (ValueError, aiohttp.ContentTypeError) as e:
                    log.API.debug(f"Raw response (status {resp.status}): {text[:500]!r}")
                    raise AuthError(f"Invalid API response (not JSON): {e}") from e

        except (aiohttp.ClientError, TimeoutError) as e:
            raise AuthError(f"Network error querying Instagram API: {e}") from e

    async def fetch_user_id(self, username: str) -> str:
        username = username.lower()
        user_data = await self._get(USER_API_URL.format(username=username))
        users = (item.get("user", {}) for item in user_data.get("users", []))
        user_id = next((u.get("pk") for u in users if u.get("username", "").lower() == username), None)
        if not user_id:
            raise UserNotFoundError(f"User '{username}' does not exist.")
        return user_id

    async def fetch_live_info(self, user_id: str) -> dict[str, Any]:
        return await self._get(LIVE_API_URL.format(user_id=user_id))

    async def fetch_story_feed_info(self, user_id: str) -> dict[str, Any]:
        return await self._get(STORY_FEED_API_URL.format(user_id=user_id))
