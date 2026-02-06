"""Thin wrapper around instagrapi that handles login, session caching,
challenge verification, and reconnection."""

from __future__ import annotations

import logging
from pathlib import Path

from instagrapi import Client
from instagrapi.exceptions import (
    ChallengeRequired,
    LoginRequired,
    TwoFactorRequired,
)

logger = logging.getLogger(__name__)

SESSION_FILE = Path("ig_session.json")


def _challenge_code_handler(username: str, choice) -> str:
    """Called by instagrapi when Instagram requires identity verification.
    Prompts the user to enter the code from their phone/email."""
    print("\n" + "=" * 60)
    print(f"Instagram requires verification for @{username}")
    print("Check your email or phone for a 6-digit code.")
    print("=" * 60)
    code = input("Enter the verification code: ").strip()
    return code


def _two_factor_handler(username: str, choice=None) -> str:
    """Called when 2FA is enabled on the account."""
    print("\n" + "=" * 60)
    print(f"Two-factor authentication required for @{username}")
    print("Check your authenticator app or SMS for the code.")
    print("=" * 60)
    code = input("Enter your 2FA code: ").strip()
    return code


class InstagramClient:
    """Manages a single authenticated Instagram session."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._cl = Client()
        self._cl.request_timeout = 30

        # Register handlers for verification challenges and 2FA
        self._cl.challenge_code_handler = _challenge_code_handler
        self._cl.change_password_handler = lambda u: None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def login(self) -> None:
        """Log in, re-using a cached session file when available."""
        if SESSION_FILE.exists():
            logger.info("Restoring session from %s", SESSION_FILE)
            self._cl.load_settings(SESSION_FILE)
            self._cl.login(self._username, self._password)
            try:
                self._cl.get_timeline_feed()
                logger.info("Session restored successfully.")
                return
            except (LoginRequired, ChallengeRequired):
                logger.warning("Cached session expired — logging in fresh.")

        logger.info("Logging in as %s …", self._username)
        try:
            self._cl.login(self._username, self._password)
        except ChallengeRequired:
            logger.info("Instagram challenge required — resolving …")
            self._cl.challenge_resolve(self._cl.last_json)
        except TwoFactorRequired:
            logger.info("Two-factor authentication required …")
            code = _two_factor_handler(self._username)
            self._cl.two_factor_login(code)

        self._cl.dump_settings(SESSION_FILE)
        logger.info("Login successful. Session saved to %s", SESSION_FILE)

    # ------------------------------------------------------------------
    # Expose the underlying instagrapi Client for direct use
    # ------------------------------------------------------------------

    @property
    def api(self) -> Client:
        """Return the raw ``instagrapi.Client`` so other modules can call any
        endpoint they need."""
        return self._cl
