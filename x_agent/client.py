"""Thin wrapper around tweepy that handles OAuth authentication,
session management, and API v2 access for X (Twitter)."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class XClient:
    """Manages an authenticated X (Twitter) API session using tweepy."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        access_token: str,
        access_token_secret: str,
        bearer_token: Optional[str] = None,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._access_token = access_token
        self._access_token_secret = access_token_secret
        self._bearer_token = bearer_token
        self._client = None
        self._api_v1 = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def login(self) -> None:
        """Authenticate with X API v2 (and v1.1 for media uploads)."""
        import tweepy

        # API v2 client (for tweets, likes, follows, etc.)
        self._client = tweepy.Client(
            consumer_key=self._api_key,
            consumer_secret=self._api_secret,
            access_token=self._access_token,
            access_token_secret=self._access_token_secret,
            bearer_token=self._bearer_token,
            wait_on_rate_limit=True,
        )

        # API v1.1 (needed for media uploads)
        auth = tweepy.OAuth1UserHandler(
            self._api_key,
            self._api_secret,
            self._access_token,
            self._access_token_secret,
        )
        self._api_v1 = tweepy.API(auth, wait_on_rate_limit=True)

        # Verify credentials
        me = self._client.get_me()
        if me and me.data:
            logger.info("Logged in to X as @%s", me.data.username)
        else:
            logger.warning("Login succeeded but could not verify user identity")

    # ------------------------------------------------------------------
    # Expose the underlying clients
    # ------------------------------------------------------------------

    @property
    def api(self):
        """Return the tweepy v2 Client."""
        if self._client is None:
            raise RuntimeError("Not authenticated. Call login() first.")
        return self._client

    @property
    def api_v1(self):
        """Return the tweepy v1.1 API (for media uploads)."""
        if self._api_v1 is None:
            raise RuntimeError("Not authenticated. Call login() first.")
        return self._api_v1
