"""Thin wrapper around the LinkedIn API that handles OAuth2 authentication
and session management.

Uses the ``linkedin-api`` package for profile-level operations and the
official REST API (via ``requests``) for publishing posts."""

from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class LinkedInClient:
    """Manages an authenticated LinkedIn API session."""

    def __init__(
        self,
        access_token: str,
        person_urn: Optional[str] = None,
    ) -> None:
        self._access_token = access_token
        self._person_urn = person_urn
        self._session: Optional[requests.Session] = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def login(self) -> None:
        """Set up an authenticated session using the provided access token.

        LinkedIn OAuth2 tokens are obtained externally via the 3-legged
        OAuth flow. This agent expects a valid access token.
        """
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": "202401",
        })

        # Resolve person URN if not provided
        if not self._person_urn:
            self._person_urn = self._get_person_urn()

        logger.info("LinkedIn client ready. Person URN: %s", self._person_urn)

    def _get_person_urn(self) -> str:
        """Fetch the authenticated user's person URN."""
        resp = self._session.get("https://api.linkedin.com/v2/userinfo")
        resp.raise_for_status()
        data = resp.json()
        sub = data.get("sub", "")
        logger.info("Authenticated as: %s %s", data.get("given_name", ""), data.get("family_name", ""))
        return f"urn:li:person:{sub}"

    # ------------------------------------------------------------------
    # Expose the session and URN
    # ------------------------------------------------------------------

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            raise RuntimeError("Not authenticated. Call login() first.")
        return self._session

    @property
    def person_urn(self) -> str:
        if not self._person_urn:
            raise RuntimeError("Not authenticated. Call login() first.")
        return self._person_urn
