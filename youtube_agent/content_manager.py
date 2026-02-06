"""Publish videos, shorts, and community posts to YouTube.

Media directory layout expected::

    media/
    ├── videos/         # .mp4 files + optional .json metadata
    ├── shorts/         # .mp4 files (vertical, < 60s)
    └── community/      # .jpg / .png images for community tab
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}


def _read_caption(media_path: Path, default_tags: List[str]) -> str:
    sidecar = media_path.with_suffix(".txt")
    generic = media_path.parent / "caption.txt"

    text = ""
    if sidecar.exists():
        text = sidecar.read_text().strip()
    elif generic.exists():
        text = generic.read_text().strip()

    if default_tags:
        tag_line = " ".join(default_tags)
        text = f"{text}\n\n{tag_line}" if text else tag_line

    return text


def _read_metadata(media_path: Path) -> dict:
    """Read optional JSON sidecar with title, description, tags, etc."""
    meta_path = media_path.with_suffix(".json")
    if meta_path.exists():
        with open(meta_path) as fh:
            return json.load(fh)
    return {}


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
    """Publishes queued media from the local file system to YouTube."""

    def __init__(
        self,
        api,
        media_dir: str | Path,
        default_tags: Optional[List[str]] = None,
        default_category_id: str = "22",
        default_privacy: str = "public",
    ) -> None:
        self._api = api
        self._media_dir = Path(media_dir)
        self._tags = default_tags or []
        self._category_id = default_category_id
        self._privacy = default_privacy

    # ------------------------------------------------------------------
    # Videos
    # ------------------------------------------------------------------

    def publish_next_video(self) -> Optional[str]:
        """Upload the oldest un-archived video in ``videos/``."""
        videos_dir = self._media_dir / "videos"
        return self._publish_from_dir(videos_dir, kind="video")

    # ------------------------------------------------------------------
    # Shorts
    # ------------------------------------------------------------------

    def publish_next_short(self) -> Optional[str]:
        """Upload the oldest un-archived short in ``shorts/``."""
        shorts_dir = self._media_dir / "shorts"
        return self._publish_from_dir(shorts_dir, kind="short")

    # ------------------------------------------------------------------
    # Community posts (image-based via unofficial workaround)
    # ------------------------------------------------------------------

    def publish_next_community_post(self) -> Optional[str]:
        """Community posts with images are not fully supported via the
        Data API v3. This creates a placeholder and logs the caption."""
        community_dir = self._media_dir / "community"
        media_path = self._next_media_file(community_dir, PHOTO_EXTENSIONS)
        if media_path is None:
            logger.info("No queued community media in %s", community_dir)
            return None

        caption = _read_caption(media_path, self._tags)
        logger.info(
            "Community post ready (manual upload needed): %s — %s",
            media_path.name, caption[:80],
        )
        _archive(media_path)
        return str(media_path)

    # ------------------------------------------------------------------
    # Direct-publish helpers (used by the calendar scheduler)
    # ------------------------------------------------------------------

    def publish_file_as_video(self, path: Path, title: str, description: str = "") -> str:
        from googleapiclient.http import MediaFileUpload

        body = {
            "snippet": {
                "title": title[:100],
                "description": description or title,
                "tags": self._tags,
                "categoryId": self._category_id,
            },
            "status": {
                "privacyStatus": self._privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(str(path), mimetype="video/*", resumable=True)
        request = self._api.videos().insert(
            part="snippet,status", body=body, media_body=media
        )
        response = request.execute()
        video_id = response["id"]
        logger.info("Published video: %s (id=%s)", path.name, video_id)
        return video_id

    def publish_file_as_short(self, path: Path, title: str, description: str = "") -> str:
        """Shorts are just vertical videos < 60s uploaded normally."""
        return self.publish_file_as_video(path, f"{title} #Shorts", description)

    def set_thumbnail(self, video_id: str, thumbnail_path: Path) -> None:
        from googleapiclient.http import MediaFileUpload

        media = MediaFileUpload(str(thumbnail_path), mimetype="image/png")
        self._api.thumbnails().set(
            videoId=video_id, media_body=media
        ).execute()
        logger.info("Set thumbnail for video %s", video_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_media_file(
        self, directory: Path, extensions: set[str] | None = None,
    ) -> Optional[Path]:
        extensions = extensions or VIDEO_EXTENSIONS
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

    def _publish_from_dir(
        self, directory: Path, kind: str,
    ) -> Optional[str]:
        media_path = self._next_media_file(directory)
        if media_path is None:
            logger.info("No queued %s media in %s", kind, directory)
            return None

        caption = _read_caption(media_path, self._tags)
        metadata = _read_metadata(media_path)
        title = metadata.get("title", caption[:100])
        description = metadata.get("description", caption)

        try:
            if kind == "short":
                video_id = self.publish_file_as_short(media_path, title, description)
            else:
                video_id = self.publish_file_as_video(media_path, title, description)

            # Set custom thumbnail if available
            thumb_path = media_path.with_suffix(".thumb.png")
            if thumb_path.exists():
                self.set_thumbnail(video_id, thumb_path)

            logger.info("Published %s (%s): %s", kind, media_path.name, video_id)
            _archive(media_path)
            return video_id

        except Exception:
            logger.exception("Failed to publish %s from %s", kind, media_path)
            return None
