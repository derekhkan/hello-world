"""Instagram Graph API client for publishing content.

Uses Meta's official Instagram Graph API instead of the private API.
No challenge_required errors since it uses OAuth tokens.

Flow for publishing a post:
1. Upload image to temporary public hosting (Graph API needs a public URL)
2. Create container: POST /{ig-user-id}/media?image_url=...&caption=...
3. Publish: POST /{ig-user-id}/media_publish?creation_id=...
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}
VIDEO_EXTENSIONS = {".mp4", ".mov"}


# ---------------------------------------------------------------------------
# Temporary file hosting (Graph API needs a public URL for media)
# ---------------------------------------------------------------------------

def _upload_to_temp_host(file_path: Path) -> Optional[str]:
    """Upload a file to temporary public hosting. Returns the public URL."""
    # Try litterbox.catbox.moe (temp hosting, 1 hour expiry)
    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                "https://litterbox.catbox.moe/resources/internals/api.php",
                data={"reqtype": "fileupload", "time": "1h"},
                files={"fileToUpload": (file_path.name, f)},
                timeout=120,
            )
        if resp.status_code == 200 and resp.text.strip().startswith("http"):
            url = resp.text.strip()
            logger.info("Uploaded %s to temp host: %s", file_path.name, url)
            return url
    except Exception as e:
        logger.warning("litterbox upload failed: %s", e)

    # Fallback: try tmpfiles.org
    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                "https://tmpfiles.org/api/v1/upload",
                files={"file": (file_path.name, f)},
                timeout=120,
            )
        if resp.status_code == 200:
            data = resp.json()
            url = data["data"]["url"].replace("tmpfiles.org/", "tmpfiles.org/dl/")
            logger.info("Uploaded %s to tmpfiles: %s", file_path.name, url)
            return url
    except Exception as e:
        logger.warning("tmpfiles upload failed: %s", e)

    return None


# ---------------------------------------------------------------------------
# Graph API Client
# ---------------------------------------------------------------------------

class GraphAPIClient:
    """Publish content to Instagram via the official Graph API."""

    def __init__(
        self,
        access_token: str,
        instagram_account_id: str,
        facebook_page_id: str = "",
    ) -> None:
        self.access_token = access_token
        self.ig_account_id = instagram_account_id
        self.page_id = facebook_page_id
        logger.info("Graph API client initialized (IG account: %s)", instagram_account_id)

    def _api_url(self, path: str) -> str:
        return f"{GRAPH_API_BASE}/{path}"

    def _post(self, endpoint: str, **params) -> dict:
        params["access_token"] = self.access_token
        resp = requests.post(self._api_url(endpoint), data=params, timeout=60)
        data = resp.json()
        if "error" in data:
            raise Exception(
                f"Graph API error: {data['error'].get('message', data['error'])}"
            )
        return data

    def _get(self, endpoint: str, **params) -> dict:
        params["access_token"] = self.access_token
        resp = requests.get(self._api_url(endpoint), params=params, timeout=60)
        data = resp.json()
        if "error" in data:
            raise Exception(
                f"Graph API error: {data['error'].get('message', data['error'])}"
            )
        return data

    # ------------------------------------------------------------------
    # Publish photo post
    # ------------------------------------------------------------------

    def publish_photo(self, image_path: Path, caption: str = "") -> str:
        """Publish a photo post. Returns the media ID."""
        image_url = _upload_to_temp_host(image_path)
        if not image_url:
            raise Exception(f"Failed to upload {image_path} to temporary hosting")

        # Step 1: Create media container
        container = self._post(
            f"{self.ig_account_id}/media",
            image_url=image_url,
            caption=caption,
        )
        container_id = container["id"]
        logger.info("Created photo container: %s", container_id)

        # Step 2: Publish
        result = self._post(
            f"{self.ig_account_id}/media_publish",
            creation_id=container_id,
        )
        media_id = result["id"]
        logger.info("Published photo post: %s", media_id)
        return media_id

    # ------------------------------------------------------------------
    # Publish reel
    # ------------------------------------------------------------------

    def publish_reel(self, video_path: Path, caption: str = "") -> str:
        """Publish a reel. Returns the media ID."""
        video_url = _upload_to_temp_host(video_path)
        if not video_url:
            raise Exception(f"Failed to upload {video_path} to temporary hosting")

        # Step 1: Create reel container
        container = self._post(
            f"{self.ig_account_id}/media",
            media_type="REELS",
            video_url=video_url,
            caption=caption,
        )
        container_id = container["id"]
        logger.info("Created reel container: %s", container_id)

        # Step 2: Wait for video processing
        self._wait_for_processing(container_id)

        # Step 3: Publish
        result = self._post(
            f"{self.ig_account_id}/media_publish",
            creation_id=container_id,
        )
        media_id = result["id"]
        logger.info("Published reel: %s", media_id)
        return media_id

    # ------------------------------------------------------------------
    # Publish story
    # ------------------------------------------------------------------

    def publish_story(self, media_path: Path) -> str:
        """Publish a story (photo or video). Returns the media ID."""
        ext = media_path.suffix.lower()
        public_url = _upload_to_temp_host(media_path)
        if not public_url:
            raise Exception(f"Failed to upload {media_path} to temporary hosting")

        params: dict = {"media_type": "STORIES"}
        if ext in VIDEO_EXTENSIONS:
            params["video_url"] = public_url
        else:
            params["image_url"] = public_url

        # Step 1: Create story container
        container = self._post(f"{self.ig_account_id}/media", **params)
        container_id = container["id"]
        logger.info("Created story container: %s", container_id)

        # Step 2: Wait for processing if video
        if ext in VIDEO_EXTENSIONS:
            self._wait_for_processing(container_id)

        # Step 3: Publish
        result = self._post(
            f"{self.ig_account_id}/media_publish",
            creation_id=container_id,
        )
        media_id = result["id"]
        logger.info("Published story: %s", media_id)
        return media_id

    # ------------------------------------------------------------------
    # Video processing wait
    # ------------------------------------------------------------------

    def _wait_for_processing(
        self, container_id: str, max_wait: int = 120
    ) -> None:
        """Poll until a video container is ready for publishing."""
        for _ in range(max_wait // 5):
            status = self._get(container_id, fields="status_code")
            code = status.get("status_code")
            if code == "FINISHED":
                logger.info("Video processing complete for %s", container_id)
                return
            if code == "ERROR":
                raise Exception(
                    f"Video processing failed for container {container_id}"
                )
            logger.info("Video processing… status=%s", code)
            time.sleep(5)
        raise Exception(
            f"Video processing timed out for container {container_id}"
        )

    # ------------------------------------------------------------------
    # Verify token
    # ------------------------------------------------------------------

    def verify(self) -> dict:
        """Verify the access token and return account info."""
        return self._get(
            self.ig_account_id,
            fields="id,username,name,profile_picture_url",
        )
