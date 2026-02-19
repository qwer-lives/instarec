import json
import time
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

    If the cookie file is valid, it is also saved as a pickled requests.Session
    so that subsequent runs can reuse it without re-reading the cookie file.
    """

    def __init__(self, cookie_file: str | Path, proxy: str | None = None):
        self.cookie_file = Path(cookie_file)
        self.proxy = proxy
        self.config_dir = user_config_path("instarec", "instarec")
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

    def _check_session_valid(self) -> bool:
        """Quick check: verify we can hit the IG API without a 401/403."""
        try:
            resp = self.session.get(_IG_BASE_URL + "accounts/current_user/?edit=true", timeout=10)
            return resp.status_code == 200
        except requests.RequestException:
            return False

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
        if resp.status_code != 200:
            raise CookieAuthError(
                f"Instagram API returned unexpected status {resp.status_code} for endpoint '{endpoint}'."
            )

        try:
            return resp.json()
        except ValueError as e:
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

    def save_cookies_from_session(self, output_path: Path) -> None:
        """
        Write the current session cookies back out as a Netscape cookie file.
        Useful after a successful instagrapi login so the cookies can be reused
        next time without a password.
        """
        jar = MozillaCookieJar(str(output_path))
        for cookie in self.session.cookies:
            jar.set_cookie(cookie)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            jar.save(ignore_discard=True, ignore_expires=True)
            log.API.info(f"Saved session cookies to: {output_path}")
        except Exception as e:
            log.API.warning(f"Could not save cookie file: {e}")


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


def get_mpd_with_cookie_fallback(
    input_value: str,
    cookie_file: Path,
    proxy: str | None,
    config_dir: Path,
) -> str:
    """
    Try to get the MPD URL using cookie-based auth first.
    If that fails, fall back to instagrapi (credentials.json).
    On a successful instagrapi login, attempt to export fresh cookies
    so they can be reused next time.

    Args:
        input_value:  Instagram username or numeric user ID.
        cookie_file:  Path to a Netscape .txt cookie file.
        proxy:        Optional proxy URL.
        config_dir:   instarec config directory (for saving exported cookies).

    Returns:
        The MPD URL string.
    """
    # --- Attempt 1: cookie-based auth ---
    log.API.info(f"Trying cookie-based authentication using: {cookie_file}")
    try:
        cookie_client = CookieClient(cookie_file=cookie_file, proxy=proxy)
        if input_value.isdigit():
            return cookie_client.get_mpd_from_user_id(input_value)
        else:
            return cookie_client.get_mpd_from_username(input_value)
    except (FileNotFoundError, CookieAuthError) as e:
        log.API.warning(f"Cookie authentication failed: {e}")
        log.API.warning("Falling back to instagrapi (credentials.json)...")

    # --- Attempt 2: instagrapi fallback ---
    ig_client = InstagramClient(proxy=proxy)

    if input_value.isdigit():
        mpd_url = ig_client.get_mpd_from_user_id(input_value)
    else:
        mpd_url = ig_client.get_mpd_from_username(input_value)

    # On success, export cookies so the user can skip the password next time
    _try_export_cookies_from_instagrapi(ig_client, cookie_file, config_dir)

    return mpd_url


def _try_export_cookies_from_instagrapi(
    ig_client: InstagramClient,
    cookie_file: Path,
    config_dir: Path,
) -> None:
    """
    After a successful instagrapi login, attempt to export the session cookies
    as a Netscape cookie file so they can be used for cookie-based auth next time.
    """
    try:
        import http.cookiejar

        settings = ig_client.client.get_settings()
        raw_cookies = settings.get("cookies", {})
        if not raw_cookies:
            log.API.debug("No cookies found in instagrapi session to export.")
            return

        jar = MozillaCookieJar(str(cookie_file))
        now = int(time.time())
        far_future = now + 60 * 60 * 24 * 365  # ~1 year

        for name, value in raw_cookies.items():
            cookie = http.cookiejar.Cookie(
                version=0,
                name=name,
                value=str(value),
                port=None,
                port_specified=False,
                domain=".instagram.com",
                domain_specified=True,
                domain_initial_dot=True,
                path="/",
                path_specified=True,
                secure=True,
                expires=far_future,
                discard=False,
                comment=None,
                comment_url=None,
                rest={},
            )
            jar.set_cookie(cookie)

        cookie_file.parent.mkdir(parents=True, exist_ok=True)
        jar.save(ignore_discard=True, ignore_expires=True)
        log.API.info(
            f"Exported session cookies to: {cookie_file}\n"
            "These will be used automatically next time instead of your password."
        )
    except Exception as e:
        log.API.debug(f"Could not export cookies from instagrapi session: {e}")
