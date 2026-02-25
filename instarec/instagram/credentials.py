import asyncio
import json
from typing import Any

from instagrapi import Client
from instagrapi.exceptions import (
    ClientNotFoundError,
    LoginRequired,
    UserNotFound,
)
from platformdirs import user_config_path

from .. import log
from .client import InstagramClient
from .exceptions import AuthError, UserNotFoundError

USER_AGENT = (
    "Instagram 416.0.0.47.66 Android (33/13; 480dpi; 1080x2400; xiaomi; M2007J20CG; surya; qcom; en_US; 641123490)"
)


class CredentialsClient(InstagramClient):
    def __init__(self, proxy: str | None = None):
        super().__init__(proxy)
        self._initialized = False
        self.config_dir = user_config_path("instarec", "instarec")
        self.credentials_path = self.config_dir / "credentials.json"
        self.session_path = self.config_dir / "session.json"

        self.client = Client()
        self.client.set_user_agent(USER_AGENT)
        if self.proxy:
            self.client.set_proxy(self.proxy)
            log.API.debug(f"Instagrapi proxy set: {self.proxy}")

    async def __aenter__(self):
        if not self._initialized:
            await asyncio.to_thread(self._initialize_session)
            self._initialized = True
        return self

    def _initialize_session(self):
        if self.session_path.exists():
            try:
                log.API.debug(f"Loading cached session from {self.session_path}")
                self.client.load_settings(self.session_path)
                return
            except Exception as e:
                log.API.warning(f"Failed to load session file: {e}, trying to log in")
        else:
            log.API.debug(f"Cached session not found at {self.session_path}, trying to log in")

        self._perform_login()

    def _load_credentials(self) -> tuple[str, str]:
        if not self.credentials_path.exists():
            log.API.critical(f"Credentials file not found at: {self.credentials_path}")
            raise FileNotFoundError(
                f"Credentials file not found at: {self.credentials_path}\n"
                "Please create a 'credentials.json' file with 'username' and 'password'."
            )
        try:
            with self.credentials_path.open("r", encoding="utf-8") as f:
                creds = json.load(f)
            return creds["username"], creds["password"]
        except (json.JSONDecodeError, KeyError) as e:
            log.API.critical(f"Error reading credentials file: {e}")
            raise AuthError(f"Invalid credentials file: {e}") from e

    def _perform_login(self):
        username, password = self._load_credentials()
        log.API.info(f"Logging in as {username}...")

        old_settings = self.client.get_settings()
        uuids = old_settings.get("uuids")

        self.client = Client()
        self.client.set_user_agent(USER_AGENT)
        if self.proxy:
            self.client.set_proxy(self.proxy)
        if uuids:
            self.client.set_uuids(uuids)
            log.API.debug("Re-using device UUIDs from previous session.")

        try:
            self.client.login(username, password)
        except Exception as e:
            raise AuthError(f"Login failed for {username}: {e}") from e

        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.client.dump_settings(self.session_path)
        log.API.debug("Login successful. Session saved.")

    def _private_request_with_retry(self, endpoint: str, retry_log_message: str, not_found_msg: str) -> dict:
        try:
            try:
                return self.client.private_request(endpoint)
            except LoginRequired as e:
                log.API.warning("Session expired or invalid, performing full re-login...")
                self._perform_login()
                log.API.debug(retry_log_message)
                try:
                    return self.client.private_request(endpoint)
                except LoginRequired:
                    raise AuthError("Login required, but re-login failed or was rejected.") from e
        except (ClientNotFoundError, UserNotFound) as e:
            raise UserNotFoundError(not_found_msg) from e
        except AuthError:
            raise
        except Exception as e:
            raise AuthError(f"Instagrapi error: {e}") from e

    async def fetch_user_id(self, username: str) -> str:
        return await asyncio.to_thread(self._fetch_user_id_sync, username)

    def _fetch_user_id_sync(self, username: str) -> str:
        user_data = self._private_request_with_retry(
            f"users/{username}/usernameinfo/",
            f"Retrying obtaining user id for '{username}'...",
            f"User '{username}' not found.",
        )
        pk = user_data.get("user", {}).get("pk")
        if not pk:
            raise UserNotFoundError(f"User '{username}' does not exist.")
        return str(pk)

    async def fetch_live_info(self, user_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._private_request_with_retry,
            f"live/web_info/?target_user_id={user_id}",
            f"Retrying MPD fetch for '{user_id}'...",
            f"User '{user_id}' not found or not currently live",
        )

    async def fetch_story_feed_info(self, user_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._private_request_with_retry,
            f"feed/user/{user_id}/story/",
            f"Retrying story feed for '{user_id}'...",
            f"Story feed for '{user_id}' not available",
        )
