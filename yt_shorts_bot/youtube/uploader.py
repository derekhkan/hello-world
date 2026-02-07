"""YouTube Data API v3 uploader for publishing Shorts.

Authentication uses OAuth 2.0 with a desktop/installed-app flow.
The user must provide a ``client_secrets.json`` from the Google Cloud Console
with the YouTube Data API v3 enabled.

Upload flow:
  1. Authenticate (or load cached token).
  2. Build a ``videos.insert`` request with resumable upload.
  3. Upload the video file.
  4. Set the video as a Short by including ``#Shorts`` in the title/description
     and ensuring the video is vertical (9:16) and ≤60 s.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from yt_shorts_bot.config import YouTubeSettings, load_settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def authenticate(settings: Optional[YouTubeSettings] = None) -> Credentials:
    """Authenticate with YouTube API and return credentials.

    Uses cached token if available; otherwise runs the OAuth consent flow.
    """
    settings = settings or load_settings().youtube
    creds: Optional[Credentials] = None
    token_path = Path(settings.token_file)

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        logger.info("Refreshing expired YouTube token")
        creds.refresh(Request())
    elif not creds or not creds.valid:
        logger.info("Running YouTube OAuth consent flow")
        secrets_path = Path(settings.client_secrets_file)
        if not secrets_path.exists():
            raise FileNotFoundError(
                f"YouTube client_secrets.json not found at {secrets_path}. "
                "Download it from the Google Cloud Console."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
        creds = flow.run_local_server(port=0)

    # Cache token for next run
    token_path.write_text(creds.to_json())
    logger.info("YouTube credentials saved to %s", token_path)
    return creds


def upload_video(
    video_path: Path,
    title: str,
    description: str,
    tags: Optional[list[str]] = None,
    settings: Optional[YouTubeSettings] = None,
) -> str:
    """Upload a video to YouTube and return the video ID.

    Parameters
    ----------
    video_path:
        Path to the .mp4 file.
    title:
        Video title (``#Shorts`` is appended automatically).
    description:
        Video description.
    tags:
        List of tags.
    settings:
        YouTube settings override.

    Returns
    -------
    The YouTube video ID (e.g. ``dQw4w9WgXcQ``).
    """
    settings = settings or load_settings().youtube
    tags = tags or settings.default_tags

    # Ensure #Shorts appears so YouTube classifies it as a Short
    if "#Shorts" not in title and "#shorts" not in title.lower():
        title = f"{title} #Shorts"
    if "#shorts" not in description.lower():
        description = f"{description}\n\n#Shorts"

    creds = authenticate(settings)
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title[:100],  # YT limit
            "description": description[:5000],
            "tags": tags,
            "categoryId": settings.category_id,
        },
        "status": {
            "privacyStatus": settings.privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10 MB chunks
    )

    logger.info("Starting YouTube upload: %s", title)
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info("Upload progress: %d%%", int(status.progress() * 100))

    video_id = response["id"]
    logger.info("Upload complete! Video ID: %s", video_id)
    logger.info("URL: https://youtube.com/shorts/%s", video_id)
    return video_id
