"""Thin wrapper around instagrapi that handles login, session caching, and
reconnection."""

from __future__ import annotations

import logging
from pathlib import Path

from instagrapi import Client
from instagrapi.exceptions import LoginRequired

logger = logging.getLogger(__name__)

SESSION_FILE = Path("ig_session.json")


class InstagramClient:
    """Manages a single authenticated Instagram session."""

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._cl = Client()
        # Realistic device / user-agent settings are already provided by
        # instagrapi; we just set a reasonable request timeout.
        self._cl.request_timeout = 30

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
                self._cl.get_timeline_feed()  # quick auth check
                logger.info("Session restored successfully.")
                return
            except LoginRequired:
                logger.warning("Cached session expired — logging in fresh.")

        logger.info("Logging in as %s …", self._username)
        self._cl.login(self._username, self._password)
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
