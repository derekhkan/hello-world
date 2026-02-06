"""Publish photos, reels, and stories from a local media directory.

Media directory layout expected::

    media/
    ├── posts/          # .jpg / .png images (or .mp4 for video posts)
    │   └── caption.txt # optional per-file caption override
    ├── reels/          # .mp4 files
    │   └── caption.txt
    └── stories/        # .jpg / .png / .mp4
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import List, Optional

from instagrapi import Client
from instagrapi.types import Media

logger = logging.getLogger(__name__)

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}
VIDEO_EXTENSIONS = {".mp4", ".mov"}


def _read_caption(media_path: Path, default_hashtags: List[str]) -> str:
    """Return a caption for *media_path*.

    Looks for a ``<stem>.txt`` sidecar file first, then falls back to
    ``caption.txt`` in the same directory, then to just the hashtags.
    """
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
    """Move a published file into an ``archive/`` subdirectory so it is not
    posted again."""
    archive_dir = media_path.parent / "archive"
    archive_dir.mkdir(exist_ok=True)
    dest = archive_dir / media_path.name
    shutil.move(str(media_path), str(dest))
    logger.info("Archived %s -> %s", media_path.name, dest)

    # Also move the sidecar caption if it exists
    sidecar = media_path.with_suffix(".txt")
    if sidecar.exists():
        shutil.move(str(sidecar), str(archive_dir / sidecar.name))


class ContentManager:
    """Publishes queued media from the local file system."""

    def __init__(
        self,
        api: Client,
        media_dir: str | Path,
        default_hashtags: Optional[List[str]] = None,
    ) -> None:
        self._api = api
        self._media_dir = Path(media_dir)
        self._hashtags = default_hashtags or []

    # ------------------------------------------------------------------
    # Posts (photo or video)
    # ------------------------------------------------------------------

    def publish_next_post(self) -> Optional[Media]:
        """Publish the oldest un-archived file in ``posts/``."""
        posts_dir = self._media_dir / "posts"
        return self._publish_from_dir(posts_dir, kind="post")

    # ------------------------------------------------------------------
    # Reels
    # ------------------------------------------------------------------

    def publish_next_reel(self) -> Optional[Media]:
        """Publish the oldest un-archived ``.mp4`` in ``reels/``."""
        reels_dir = self._media_dir / "reels"
        return self._publish_from_dir(reels_dir, kind="reel")

    # ------------------------------------------------------------------
    # Stories
    # ------------------------------------------------------------------

    def publish_next_story(self) -> Optional[Media]:
        """Publish the oldest un-archived file in ``stories/``."""
        stories_dir = self._media_dir / "stories"
        return self._publish_from_dir(stories_dir, kind="story")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_media_file(self, directory: Path) -> Optional[Path]:
        """Return the oldest media file in *directory* that hasn't been
        archived yet, or ``None``."""
        if not directory.exists():
            return None
        candidates = sorted(
            (
                p
                for p in directory.iterdir()
                if p.is_file()
                and p.suffix.lower() in PHOTO_EXTENSIONS | VIDEO_EXTENSIONS
            ),
            key=lambda p: p.stat().st_mtime,
        )
        return candidates[0] if candidates else None

    def _publish_from_dir(
        self, directory: Path, kind: str
    ) -> Optional[Media]:
        media_path = self._next_media_file(directory)
        if media_path is None:
            logger.info("No queued %s media in %s", kind, directory)
            return None

        caption = _read_caption(media_path, self._hashtags)
        ext = media_path.suffix.lower()

        try:
            if kind == "post":
                media = self._upload_post(media_path, caption, ext)
            elif kind == "reel":
                media = self._upload_reel(media_path, caption)
            elif kind == "story":
                media = self._upload_story(media_path, ext)
            else:
                raise ValueError(f"Unknown media kind: {kind}")

            logger.info(
                "Published %s (%s): %s", kind, media_path.name, media.pk
            )
            _archive(media_path)
            return media

        except Exception:
            logger.exception("Failed to publish %s from %s", kind, media_path)
            return None

    # ------------------------------------------------------------------
    # Direct-publish helpers (used by the calendar scheduler)
    # ------------------------------------------------------------------

    def publish_file_as_post(self, path: Path, caption: str) -> Media:
        """Publish a specific file as a post (used by the content calendar)."""
        ext = path.suffix.lower()
        if self._hashtags:
            caption = f"{caption}\n\n{' '.join(self._hashtags)}"
        media = self._upload_post(path, caption, ext)
        logger.info("Published post from calendar: %s (pk=%s)", path.name, media.pk)
        return media

    def publish_file_as_reel(self, path: Path, caption: str) -> Media:
        """Publish a specific file as a reel (used by the content calendar)."""
        if self._hashtags:
            caption = f"{caption}\n\n{' '.join(self._hashtags)}"
        media = self._upload_reel(path, caption)
        logger.info("Published reel from calendar: %s (pk=%s)", path.name, media.pk)
        return media

    def publish_file_as_story(self, path: Path) -> Media:
        """Publish a specific file as a story (used by the content calendar)."""
        ext = path.suffix.lower()
        media = self._upload_story(path, ext)
        logger.info("Published story from calendar: %s (pk=%s)", path.name, media.pk)
        return media

    # ------------------------------------------------------------------
    # Low-level upload helpers
    # ------------------------------------------------------------------

    def _upload_post(
        self, path: Path, caption: str, ext: str
    ) -> Media:
        if ext in PHOTO_EXTENSIONS:
            return self._api.photo_upload(path, caption)
        return self._api.video_upload(path, caption)

    def _upload_reel(self, path: Path, caption: str) -> Media:
        return self._api.clip_upload(path, caption)

    def _upload_story(self, path: Path, ext: str) -> Media:
        if ext in PHOTO_EXTENSIONS:
            return self._api.photo_upload_to_story(path)
        return self._api.video_upload_to_story(path)
