from abc import ABC, abstractmethod
from typing import Any

from .. import log
from .exceptions import UserNotFoundError, UserNotLiveError


class InstagramClient(ABC):
    def __init__(self, proxy: str | None = None):
        self.proxy = proxy

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return

    @abstractmethod
    async def fetch_user_id(self, username: str) -> str:
        pass

    @abstractmethod
    async def fetch_live_info(self, user_id: str) -> dict[str, Any]:
        pass

    @abstractmethod
    async def fetch_story_feed_info(self, user_id: str) -> dict[str, Any]:
        pass

    async def get_mpd(self, identifier: str) -> str:
        if not identifier.isdigit():
            log.API.debug(f"Resolving user ID for username: '{identifier}'")
            user_id = await self.fetch_user_id(identifier)
        else:
            user_id = identifier

        log.API.info(f"Checking live status for {user_id}...")
        try:
            live_info = await self.fetch_live_info(user_id)
            if mpd_url := live_info.get("dash_abr_playback_url"):
                log.API.info(f"Found MPD for {user_id}: {mpd_url}")
                return mpd_url
        except UserNotFoundError:
            log.API.info("User doesn't seem to be live")

        log.API.info("Checking their story feed in case they are a co-host...")
        story_feed_info = await self.fetch_story_feed_info(user_id)
        if (broadcast := story_feed_info.get("broadcast")) and (mpd_url := broadcast.get("dash_abr_playback_url")):
            host = broadcast.get("broadcast_owner", {})
            host_username = host.get("username", user_id)
            log.API.info(f"Found broadcast via story feed (host: {host_username}): {mpd_url}")
            return mpd_url

        raise UserNotLiveError(f"{identifier} is not currently live.")
