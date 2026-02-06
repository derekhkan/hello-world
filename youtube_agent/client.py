"""Thin wrapper around the YouTube Data API v3 that handles OAuth2
authentication, token caching, and reconnection."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

TOKEN_FILE = Path("yt_token.json")
CREDENTIALS_FILE = Path("client_secrets.json")

# Required OAuth2 scopes for full YouTube management
SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


class YouTubeClient:
    """Manages an authenticated YouTube API session."""

    def __init__(
        self,
        client_secrets_file: str = "client_secrets.json",
        api_key: Optional[str] = None,
    ) -> None:
        self._secrets_file = Path(client_secrets_file)
        self._api_key = api_key
        self._youtube = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def login(self) -> None:
        """Authenticate via OAuth2, re-using a cached token when available."""
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds: Optional[Credentials] = None

        if TOKEN_FILE.exists():
            logger.info("Restoring YouTube session from %s", TOKEN_FILE)
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired YouTube token …")
                creds.refresh(Request())
            else:
                if not self._secrets_file.exists():
                    raise FileNotFoundError(
                        f"OAuth2 client secrets file not found: {self._secrets_file}\n"
                        "Download it from Google Cloud Console → APIs & Services → Credentials"
                    )
                logger.info("Starting YouTube OAuth2 flow …")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self._secrets_file), SCOPES
                )
                creds = flow.run_local_server(port=0)

            TOKEN_FILE.write_text(creds.to_json())
            logger.info("YouTube token saved to %s", TOKEN_FILE)

        self._youtube = build("youtube", "v3", credentials=creds)
        logger.info("YouTube API client ready.")

    def login_api_key(self) -> None:
        """Authenticate with a simple API key (read-only operations)."""
        from googleapiclient.discovery import build

        if not self._api_key:
            raise ValueError("YouTube API key is required for API-key auth")
        self._youtube = build("youtube", "v3", developerKey=self._api_key)
        logger.info("YouTube API client ready (API key mode — read-only).")

    # ------------------------------------------------------------------
    # Expose the underlying YouTube API resource
    # ------------------------------------------------------------------

    @property
    def api(self):
        """Return the raw ``googleapiclient`` YouTube resource."""
        if self._youtube is None:
            raise RuntimeError("Not authenticated. Call login() first.")
        return self._youtube
