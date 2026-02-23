import json

from instagrapi import Client
from instagrapi.exceptions import (
    ClientNotFoundError,
    LoginRequired,
)
from instagrapi.exceptions import (
    UserNotFound as IgUserNotFound,
)
from platformdirs import user_config_path

from .. import log
from .exceptions import AuthError, UserNotFound, UserNotLiveError

USER_AGENT = (
    "Instagram 416.0.0.47.66 Android (33/13; 480dpi; 1080x2400; xiaomi; M2007J20CG; surya; qcom; en_US; 641123490)"
)


class CredentialsClient:
    def __init__(self, proxy: str | None = None):
        self.proxy = proxy
        self.config_dir = user_config_path("instarec", "instarec")
        self.credentials_path = self.config_dir / "credentials.json"
        self.session_path = self.config_dir / "session.json"

        self.client = Client()
        self.client.set_user_agent(USER_AGENT)
        if self.proxy:
            self.client.set_proxy(self.proxy)
            log.API.debug(f"Instagrapi proxy set: {self.proxy}")

        if self.session_path.exists():
            try:
                log.API.debug(f"Loading cached session from {self.session_path}")
                self.client.load_settings(self.session_path)
            except Exception as e:
                log.API.warning(f"Failed to load session file: {e}, trying to log in")
                self._perform_login()
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
        if self.proxy:
            self.client.set_proxy(self.proxy)
            log.API.debug(f"Instagrapi proxy set: {self.proxy}")
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
        except (ClientNotFoundError, IgUserNotFound) as e:
            raise UserNotFound(not_found_msg) from e
        except AuthError:
            raise
        except Exception as e:
            raise AuthError(f"Instagrapi error: {e}") from e

    def get_mpd(self, identifier: str) -> str:
        if not identifier.isdigit():
            log.API.debug(f"Resolving user ID for username: '{identifier}'")
            user_data = self._private_request_with_retry(
                f"users/{identifier}/usernameinfo/",
                f"Retrying obtaining user id for '{identifier}'...",
                f"User '{identifier}' not found.",
            )
            if not user_data.get("user", {}).get("pk"):
                raise UserNotFound(f"User '{identifier}' does not exist.")
            identifier = user_data.get("user", {}).get("pk")

        log.API.debug(f"Checking live status for {identifier}...")
        live_data = self._private_request_with_retry(
            f"live/web_info/?target_user_id={identifier}",
            f"Retrying MPD fetch for '{identifier}'...",
            f"User '{identifier}' not found or not currently live",
        )
        if mpd_url := live_data.get("dash_abr_playback_url"):
            log.API.info(f"Found MPD for {identifier}: {mpd_url}")
            return mpd_url

        # The user may be a guest in a co-broadcast hosted by someone else.
        # In that case the response won't have an MPD URL but may contain
        # broadcast_owner pointing to the actual host.
        broadcast_owner = live_data.get("broadcast_owner")
        if broadcast_owner:
            host_id = str(broadcast_owner.get("pk", ""))
            if host_id and host_id != str(identifier):
                host_username = broadcast_owner.get("username", host_id)
                log.API.info(
                    f"{identifier} is a guest in a co-broadcast hosted by {host_username}. "
                    f"Fetching host's broadcast..."
                )
                host_data = self._private_request_with_retry(
                    f"live/web_info/?target_user_id={host_id}",
                    f"Retrying MPD fetch for co-broadcast host '{host_id}'...",
                    f"Co-broadcast host '{host_id}' not found or not currently live",
                )
                if mpd_url := host_data.get("dash_abr_playback_url"):
                    log.API.info(f"Found MPD via co-broadcast host {host_username}: {mpd_url}")
                    return mpd_url

        raise UserNotLiveError(f"{identifier} is not currently live.")
