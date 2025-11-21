import json
from pathlib import Path

from instagrapi import Client
from instagrapi.exceptions import ClientNotFoundError, LoginRequired, PrivateError, UserNotFound
from platformdirs import user_config_path

from . import log


class UserNotLiveError(Exception):
    pass


class InstagramClient:
    def __init__(self, proxy: str | None = None):
        self.client = Client()
        if proxy:
            self.client.set_proxy(proxy)
            log.API.debug(f"Instagrapi proxy set: {proxy}")
        self.config_dir = user_config_path("instarec", "instarec")
        self.credentials_file_path = self.config_dir / "credentials.json"
        self.session_file_path = self.config_dir / "session.json"
        self.username, self.password = self._load_credentials()

    def _raise_value_error_exception(self, msg):
        raise ValueError(msg)

    def _load_credentials(self) -> tuple[str, str]:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        try:
            with self.credentials_file_path.open("r", encoding="utf-8") as f:
                creds = json.load(f)
            username = creds.get("username")
            password = creds.get("password")
            if not username or not password:
                self._raise_value_error_exception("'username' and/or 'password' not found in credentials file.")
            return username, password
        except FileNotFoundError as e:
            log.API.critical(f"Credentials file not found at: {self.credentials_file_path}")
            raise FileNotFoundError(
                f"Please create a 'credentials.json' file at '{self.credentials_file_path}' with your "
                "Instagram username and password.\n\n"
                "Example format:\n"
                '{\n  "username": "your_instagram_username",\n  "password": "your_instagram_password"\n}'
            ) from e
        except (json.JSONDecodeError, ValueError) as e:
            log.API.critical(f"Error reading credentials file: {e}")
            raise ValueError(
                f"Could not parse {self.credentials_file_path}. Ensure it is valid JSON. Error: {e}"
            ) from e

    def _login_and_get_mpd(self, user_id: str) -> str:
        if self.session_file_path.exists():
            log.API.debug(f"Loading session from {self.session_file_path}")
            self.client.load_settings(self.session_file_path)

        try:
            log.API.debug("Attempting to fetch MPD with current session...")
            live_data = self.client.private_request(f"live/web_info/?target_user_id={user_id}")
            log.API.debug("Session is valid.")
            return live_data.get("dash_abr_playback_url")
        except LoginRequired:
            log.API.warning("Session is invalid or expired. Performing a full re-login...")

            old_settings = self.client.get_settings()
            uuids = old_settings.get("uuids")

            self.client = Client()
            if uuids:
                self.client.set_uuids(uuids)
                log.API.debug("Re-using device UUIDs from previous session.")

            self.client.login(self.username, self.password)
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self.client.dump_settings(self.session_file_path)
            log.API.info("Successfully re-logged in and saved new session.")

            log.API.debug(f"Retrying MPD fetch for '{user_id}'...")
            live_data = self.client.private_request(f"live/web_info/?target_user_id={user_id}")
            return live_data.get("dash_abr_playback_url")
        except (UserNotFound, PrivateError) as e:
            log.API.error(f"Could not MPD for user id'{user_id}': {e}")
            raise

    def get_live_mpd_url(self, target_username: str) -> str:
        try:
            user_data = self.client.private_request(f"users/web_profile_info/?username={target_username}")
        except ClientNotFoundError as e:
            raise UserNotLiveError(f"Instagram user '{target_username}' does not exist.") from e

        user_id = user_data.get("data", {}).get("user", {}).get("id")

        log.API.debug(f"Checking live status for user ID: {user_id}...")
        mpd_url = self._login_and_get_mpd(user_id)
        if not mpd_url:
            raise UserNotLiveError(f"User '{target_username}' appears to be live, but no MPD URL was found.")

        log.API.info(f"Found live stream for '{target_username}': {mpd_url}")
        return mpd_url
