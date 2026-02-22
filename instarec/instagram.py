import json
from http.cookiejar import MozillaCookieJar
from pathlib import Path

import requests
from instagrapi import Client
from instagrapi.exceptions import ClientNotFoundError, LoginRequired, PrivateError, UserNotFound
from platformdirs import user_config_path

from . import log

# Instagram web API constants
_IG_BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "x-ig-app-id": "936619743392459",
}
_IG_BASE_URL = "https://www.instagram.com/api/v1/"


class UserNotLiveError(Exception):
    pass


class CookieAuthError(Exception):
    """Raised when cookie-based authentication fails."""
    pass


class CookieClient:
    """
    Authenticates with Instagram using a Netscape-format cookie file (.txt)
    and queries the Instagram web API directly (no instagrapi required).

    """

    def __init__(self, cookie_file: str | Path, proxy: str | None = None):
        self.cookie_file = Path(cookie_file)
        self.proxy = proxy
        self.session = self._build_session()

    def _build_session(self) -> requests.Session:
        """Load the Netscape cookie file and build an authenticated requests.Session."""
        if not self.cookie_file.exists():
            raise FileNotFoundError(
                f"Cookie file not found: {self.cookie_file}\n"
                "Export your Instagram cookies as a Netscape-format .txt file "
                "(e.g. using the 'Get cookies.txt LOCALLY' browser extension) "
                "and pass the path with --cookies."
            )

        log.API.debug(f"Loading cookies from: {self.cookie_file}")
        jar = MozillaCookieJar(str(self.cookie_file))
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
        except Exception as e:
            raise CookieAuthError(f"Could not parse cookie file '{self.cookie_file}': {e}") from e

        session = requests.Session()
        session.cookies.update(jar)
        session.headers.update(_IG_BASE_HEADERS)

        # Inject CSRF token from cookies into request headers (required by IG API)
        csrf_token = session.cookies.get("csrftoken")
        if csrf_token:
            session.headers.update({"x-csrftoken": csrf_token})
        else:
            log.API.warning(
                "No 'csrftoken' found in cookie file. "
                "API calls may fail — ensure you are logged in when exporting cookies."
            )

        if self.proxy:
            session.proxies = {"http": self.proxy, "https": self.proxy}
            log.API.debug(f"Cookie session proxy set: {self.proxy}")

        log.API.debug("Cookie session built successfully.")
        return session

    def _get(self, endpoint: str) -> dict:
        """GET an Instagram API endpoint and return parsed JSON."""
        url = _IG_BASE_URL + endpoint
        log.API.debug(f"Cookie GET: {url}")
        try:
            resp = self.session.get(url, timeout=15)
        except requests.RequestException as e:
            raise CookieAuthError(f"Network error querying Instagram API: {e}") from e

        if resp.status_code == 401:
            raise CookieAuthError(
                "Instagram returned 401 Unauthorized. "
                "Your cookies are likely expired or invalid. "
                "Please export fresh cookies and try again."
            )
        if resp.status_code == 403:
            raise CookieAuthError(
                "Instagram returned 403 Forbidden. "
                "Your cookies may be invalid or your account may be restricted."
            )
        if resp.status_code == 404:
            raise UserNotLiveError(
                f"Instagram returned 404 for endpoint '{endpoint}'. "
                "The user is likely not live."
            )
        if resp.status_code != 200:
            raise CookieAuthError(
                f"Instagram API returned unexpected status {resp.status_code} for endpoint '{endpoint}'."
            )

        # A redirect to the login page returns 200 HTML — detect it before trying JSON.
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" in content_type or resp.text.lstrip().startswith("<!DOCTYPE"):
            log.API.debug(f"Raw response (status {resp.status_code}): {resp.text[:500]!r}")
            raise CookieAuthError(
                "Instagram redirected to the login page instead of returning API data. "
                "Your cookies are likely expired or invalid. "
                "Please export fresh cookies and try again."
            )

        try:
            return resp.json()
        except ValueError as e:
            log.API.debug(f"Raw response (status {resp.status_code}): {resp.text[:500]!r}")
            raise CookieAuthError(f"Could not parse Instagram API response as JSON: {e}") from e

    def _get_user_id_from_username(self, username: str) -> str:
        log.API.debug(f"Resolving user ID for username: '{username}'")
        data = self._get(f"users/web_profile_info/?username={username}")
        user_id = data.get("data", {}).get("user", {}).get("id")
        if not user_id:
            raise UserNotLiveError(f"Instagram user '{username}' does not exist or could not be resolved.")
        log.API.debug(f"Resolved '{username}' -> user ID {user_id}")
        return user_id

    def _get_mpd_for_user_id(self, user_id: str) -> str | None:
        data = self._get(f"live/web_info/?target_user_id={user_id}")
        return data.get("dash_abr_playback_url")

    def get_mpd_from_username(self, target_username: str) -> str:
        user_id = self._get_user_id_from_username(target_username)
        return self.get_mpd_from_user_id(user_id, _resolved_username=target_username)

    def get_mpd_from_user_id(self, user_id: str, _resolved_username: str | None = None) -> str:
        label = f"'{_resolved_username}'" if _resolved_username else f"user ID {user_id}"
        log.API.debug(f"Fetching live stream MPD for {label}...")
        mpd_url = self._get_mpd_for_user_id(user_id)
        if not mpd_url:
            raise UserNotLiveError(f"User {label} does not appear to be live (no MPD URL returned).")
        log.API.info(f"Found live stream for {label}: {mpd_url}")
        return mpd_url


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

    def get_mpd_from_username(self, target_username: str) -> str:
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

    def get_mpd_from_user_id(self, user_id: str) -> str:
        log.API.debug(f"Checking live status for user ID: {user_id}...")
        mpd_url = self._login_and_get_mpd(user_id)
        if not mpd_url:
            raise UserNotLiveError(f"User with ID {user_id} appears to be live, but no MPD URL was found.")

        log.API.info(f"Found live stream for user with ID '{user_id}': {mpd_url}")
        return mpd_url
