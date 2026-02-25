class InstagramError(Exception):
    """Base class for all Instagram-related errors."""


class UserNotLiveError(InstagramError):
    """Raised when the user is found but is not currently live."""


class UserNotFoundError(InstagramError):
    """Raised when the username or user ID cannot be resolved."""


class AuthError(InstagramError):
    """Raised when authentication fails (invalid cookies, bad password, etc.)."""


class MissingDependencyError(InstagramError):
    """Raised when a required optional dependency (like instagrapi) is missing."""
