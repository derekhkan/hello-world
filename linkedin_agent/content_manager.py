"""Publish posts, articles, and carousels to LinkedIn via the REST API.

Media directory layout expected::

    media/
    ├── posts/          # .jpg / .png images for post attachments
    ├── articles/       # .jpg / .png cover images + .txt body
    └── carousels/      # .pdf files for document/carousel posts
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}
DOCUMENT_EXTENSIONS = {".pdf"}
API_BASE = "https://api.linkedin.com/v2"


def _read_caption(media_path: Path, default_hashtags: List[str]) -> str:
    sidecar = media_path.with_suffix(".txt")
    generic = media_path.parent / "caption.txt"

    text = ""
    if sidecar.exists():
        text = sidecar.read_text().strip()
    elif generic.exists():
        text = generic.read_text().strip()

    if default_hashtags:
        tag_line = " ".join(default_hashtags)
        text = f"{text}\n\n{tag_line}" if text else tag_line

    return text


def _archive(media_path: Path) -> None:
    archive_dir = media_path.parent / "archive"
    archive_dir.mkdir(exist_ok=True)
    dest = archive_dir / media_path.name
    shutil.move(str(media_path), str(dest))
    logger.info("Archived %s -> %s", media_path.name, dest)

    for ext in (".txt", ".json"):
        sidecar = media_path.with_suffix(ext)
        if sidecar.exists():
            shutil.move(str(sidecar), str(archive_dir / sidecar.name))


class ContentManager:
    """Publishes queued content from the local file system to LinkedIn."""

    def __init__(
        self,
        session: requests.Session,
        person_urn: str,
        media_dir: str | Path,
        default_hashtags: Optional[List[str]] = None,
    ) -> None:
        self._session = session
        self._person_urn = person_urn
        self._media_dir = Path(media_dir)
        self._hashtags = default_hashtags or []

    # ------------------------------------------------------------------
    # Posts
    # ------------------------------------------------------------------

    def publish_next_post(self) -> Optional[str]:
        """Publish the oldest un-archived image post from ``posts/``."""
        posts_dir = self._media_dir / "posts"
        return self._publish_from_dir(posts_dir, kind="post")

    # ------------------------------------------------------------------
    # Articles (text post with link — full articles need LinkedIn's editor)
    # ------------------------------------------------------------------

    def publish_next_article(self) -> Optional[str]:
        """Publish an article-style post from ``articles/``."""
        articles_dir = self._media_dir / "articles"
        return self._publish_from_dir(articles_dir, kind="article")

    # ------------------------------------------------------------------
    # Carousels (PDF document posts)
    # ------------------------------------------------------------------

    def publish_next_carousel(self) -> Optional[str]:
        """Publish a carousel/document post from ``carousels/``."""
        carousels_dir = self._media_dir / "carousels"
        media_path = self._next_media_file(carousels_dir, DOCUMENT_EXTENSIONS | PHOTO_EXTENSIONS)
        if media_path is None:
            logger.info("No queued carousel media in %s", carousels_dir)
            return None

        caption = _read_caption(media_path, self._hashtags)

        try:
            post_id = self.publish_text_post(caption)
            logger.info("Published carousel post (text-only fallback): %s", post_id)
            _archive(media_path)
            return post_id
        except Exception:
            logger.exception("Failed to publish carousel from %s", media_path)
            return None

    # ------------------------------------------------------------------
    # Direct-publish helpers (used by the calendar scheduler)
    # ------------------------------------------------------------------

    def publish_text_post(self, text: str) -> str:
        """Publish a text-only post to LinkedIn."""
        body = {
            "author": self._person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": text,
                    },
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC",
            },
        }

        resp = self._session.post(f"{API_BASE}/ugcPosts", json=body)
        resp.raise_for_status()
        post_id = resp.json().get("id", "unknown")
        logger.info("Published text post: %s", post_id)
        return post_id

    def publish_image_post(self, text: str, image_path: Path) -> str:
        """Upload an image and publish a post with it."""
        # Step 1: Register upload
        register_body = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": self._person_urn,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent",
                    }
                ],
            }
        }

        register_resp = self._session.post(
            f"{API_BASE}/assets?action=registerUpload", json=register_body
        )
        register_resp.raise_for_status()
        register_data = register_resp.json()

        upload_url = register_data["value"]["uploadMechanism"][
            "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
        ]["uploadUrl"]
        asset = register_data["value"]["asset"]

        # Step 2: Upload the image
        with open(image_path, "rb") as f:
            upload_resp = self._session.put(
                upload_url,
                data=f,
                headers={"Content-Type": "application/octet-stream"},
            )
            upload_resp.raise_for_status()

        # Step 3: Create the post with the image
        body = {
            "author": self._person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": text,
                    },
                    "shareMediaCategory": "IMAGE",
                    "media": [
                        {
                            "status": "READY",
                            "media": asset,
                        }
                    ],
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC",
            },
        }

        resp = self._session.post(f"{API_BASE}/ugcPosts", json=body)
        resp.raise_for_status()
        post_id = resp.json().get("id", "unknown")
        logger.info("Published image post: %s", post_id)
        return post_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_media_file(
        self, directory: Path, extensions: Optional[set[str]] = None,
    ) -> Optional[Path]:
        extensions = extensions or PHOTO_EXTENSIONS
        if not directory.exists():
            return None
        candidates = sorted(
            (
                p for p in directory.iterdir()
                if p.is_file() and p.suffix.lower() in extensions
            ),
            key=lambda p: p.stat().st_mtime,
        )
        return candidates[0] if candidates else None

    def _publish_from_dir(self, directory: Path, kind: str) -> Optional[str]:
        media_path = self._next_media_file(directory)
        if media_path is None:
            logger.info("No queued %s media in %s", kind, directory)
            return None

        caption = _read_caption(media_path, self._hashtags)

        try:
            if media_path.suffix.lower() in PHOTO_EXTENSIONS:
                post_id = self.publish_image_post(caption, media_path)
            else:
                post_id = self.publish_text_post(caption)

            logger.info("Published %s (%s): %s", kind, media_path.name, post_id)
            _archive(media_path)
            return post_id

        except Exception:
            logger.exception("Failed to publish %s from %s", kind, media_path)
            return None
