from http.cookiejar import MozillaCookieJar
from pathlib import Path

import aiohttp
from aiohttp_socks import ProxyConnector

from .. import log
from .exceptions import AuthError, InstagramError, UserNotFound, UserNotLiveError

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
STORY_FEED_URL = "https://www.instagram.com/api/v1/feed/user/{user_id}/story/"
REELS_TRAY_URL = "https://www.instagram.com/api/v1/live/reels_tray_broadcasts/"


class CookieClient:
    def __init__(self, cookie_file: str, proxy: str | None = None):
        self.cookie_file = Path(cookie_file)
        self.proxy = proxy

        if not self.cookie_file.exists():
            raise FileNotFoundError(f"Cookie file not found: {self.cookie_file}")

        log.API.debug(f"Loading cookies from: {self.cookie_file}")
        jar = MozillaCookieJar(str(self.cookie_file))
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
        except Exception as e:
            raise AuthError(f"Could not parse cookie file: {e}") from e

        self.cookies = {cookie.name: cookie.value for cookie in jar}
        self.headers = dict(BASE_HEADERS)
        if csrf_token := self.cookies.get("csrftoken"):
            self.headers["x-csrftoken"] = csrf_token
        else:
            log.API.warning("No 'csrftoken' found in cookies. API calls may fail.")
        log.API.debug("Cookie session built successfully.")

    async def _get(self, session: aiohttp.ClientSession, url: str) -> dict:
        log.API.debug(f"Cookie GET: {url}")
        try:
            async with session.get(url, timeout=10) as resp:
                if resp.status in (401, 403):
                    raise AuthError(
                        f"Authentication failed (Status {resp.status}). Your cookies are likely expired or invalid."
                    )
                if resp.status == 404:
                    raise UserNotLiveError(f"Instagram returned 404 for {url}")
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

    async def get_mpd(self, identifier: str) -> str:
        connector = None
        if self.proxy:
            connector = ProxyConnector.from_url(self.proxy)
            log.API.debug(f"Cookie session proxy set: {self.proxy}")

        async with aiohttp.ClientSession(connector=connector, headers=self.headers, cookies=self.cookies) as session:
            if not identifier.isdigit():
                log.API.debug(f"Resolving user ID for username: '{identifier}'")
                user_data = await self._get(session, USER_API_URL.format(username=identifier))
                users = (item.get("user", {}) for item in user_data.get("users", []))
                user_id = next((u.get("pk") for u in users if u.get("username", "").lower() == identifier), None)
                if not user_id:
                    raise UserNotFound(f"User '{identifier}' does not exist.")
                identifier = user_id

            log.API.info(f"Checking live status for {identifier}...")
            # A 404 means the user isn't hosting a broadcast; catch it so we can
            # still attempt the co-broadcast fallbacks below.
            try:
                live_data = await self._get(session, LIVE_API_URL.format(user_id=identifier))
            except UserNotLiveError:
                live_data = {}

            if mpd_url := live_data.get("dash_abr_playback_url"):
                log.API.info(f"Found MPD for {identifier}: {mpd_url}")
                return mpd_url

            # The user may be a guest in a co-broadcast hosted by someone else.
            # Some API versions return the host's broadcast object even when
            # querying a guest; check broadcast_owner for that case.
            broadcast_owner = live_data.get("broadcast_owner")
            if broadcast_owner:
                host_id = str(broadcast_owner.get("pk", ""))
                if host_id and host_id != str(identifier):
                    host_username = broadcast_owner.get("username", host_id)
                    log.API.info(
                        f"{identifier} is a guest in a co-broadcast hosted by {host_username}. "
                        f"Fetching host's broadcast..."
                    )
                    host_data = await self._get(session, LIVE_API_URL.format(user_id=host_id))
                    if mpd_url := host_data.get("dash_abr_playback_url"):
                        log.API.info(f"Found MPD via co-broadcast host {host_username}: {mpd_url}")
                        return mpd_url

            # Try the user's story feed — Instagram includes a "broadcast"
            # field when the user is in any live broadcast (host or guest).
            # Unlike the reels tray this works for any user, not just followed accounts.
            log.API.debug(f"Checking story feed for {identifier}'s broadcast...")
            try:
                story_data = await self._get(session, STORY_FEED_URL.format(user_id=identifier))
                broadcast = story_data.get("broadcast")
                if broadcast:
                    if mpd_url := broadcast.get("dash_abr_playback_url"):
                        host = broadcast.get("broadcast_owner", {})
                        host_username = host.get("username", identifier)
                        log.API.info(f"Found broadcast via story feed (host: {host_username}): {mpd_url}")
                        return mpd_url
            except (UserNotLiveError, AuthError, InstagramError):
                log.API.debug("Story feed lookup failed.")

            # Last resort: search the reels tray for the user appearing as a
            # co-broadcaster in someone else's active broadcast.
            # Note: limited to broadcasts by accounts the authenticated user follows.
            log.API.debug(f"Searching reels tray for {identifier} as a co-broadcaster...")
            try:
                reels_data = await self._get(session, REELS_TRAY_URL)
                for broadcast in reels_data.get("broadcasts", []):
                    for co in broadcast.get("cobroadcasters", []):
                        if str(co.get("pk", "")) == str(identifier):
                            host = broadcast.get("broadcast_owner", {})
                            host_id = str(host.get("pk", ""))
                            host_username = host.get("username", host_id)
                            log.API.info(
                                f"Found {identifier} as guest in {host_username}'s broadcast. "
                                f"Fetching host's broadcast..."
                            )
                            if mpd_url := broadcast.get("dash_abr_playback_url"):
                                log.API.info(f"Found MPD via reels tray host {host_username}: {mpd_url}")
                                return mpd_url
                            host_data = await self._get(session, LIVE_API_URL.format(user_id=host_id))
                            if mpd_url := host_data.get("dash_abr_playback_url"):
                                log.API.info(f"Found MPD via reels tray host {host_username}: {mpd_url}")
                                return mpd_url
            except (UserNotLiveError, AuthError, InstagramError):
                log.API.debug("Reels tray lookup failed.")

            raise UserNotLiveError(f"{identifier} is not currently live.")
