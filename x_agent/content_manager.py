"""Publish tweets, threads, and media posts to X (Twitter).

Media directory layout expected::

    media/
    ├── tweets/         # .png / .jpg images for tweet attachments
    ├── threads/        # .json thread definitions + images
    └── media_posts/    # .png / .jpg standalone media posts
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif"}


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
    """Publishes queued content from the local file system to X."""

    def __init__(
        self,
        api,
        api_v1,
        media_dir: str | Path,
        default_hashtags: Optional[List[str]] = None,
    ) -> None:
        self._api = api        # tweepy v2 Client
        self._api_v1 = api_v1  # tweepy v1.1 API (for media uploads)
        self._media_dir = Path(media_dir)
        self._hashtags = default_hashtags or []

    # ------------------------------------------------------------------
    # Tweets
    # ------------------------------------------------------------------

    def publish_next_tweet(self) -> Optional[str]:
        """Post the oldest un-archived tweet from ``tweets/``."""
        tweets_dir = self._media_dir / "tweets"
        return self._publish_from_dir(tweets_dir, kind="tweet")

    # ------------------------------------------------------------------
    # Threads
    # ------------------------------------------------------------------

    def publish_next_thread(self) -> Optional[str]:
        """Post a thread from ``threads/``."""
        threads_dir = self._media_dir / "threads"
        return self._publish_from_dir(threads_dir, kind="thread")

    # ------------------------------------------------------------------
    # Media posts
    # ------------------------------------------------------------------

    def publish_next_media_post(self) -> Optional[str]:
        """Post a standalone media tweet from ``media_posts/``."""
        media_dir = self._media_dir / "media_posts"
        return self._publish_from_dir(media_dir, kind="media_post")

    # ------------------------------------------------------------------
    # Direct-publish helpers (used by the calendar scheduler)
    # ------------------------------------------------------------------

    def publish_tweet(self, text: str, media_path: Optional[Path] = None) -> str:
        media_ids = None
        if media_path and media_path.exists():
            media_ids = [self._upload_media(media_path)]

        response = self._api.create_tweet(text=text[:280], media_ids=media_ids)
        tweet_id = response.data["id"]
        logger.info("Published tweet: %s", tweet_id)
        return tweet_id

    def publish_thread(self, tweets: List[str], media_paths: Optional[List[Path]] = None) -> List[str]:
        """Post a series of tweets as a thread (reply chain)."""
        tweet_ids = []
        reply_to = None

        for i, text in enumerate(tweets):
            media_ids = None
            if media_paths and i < len(media_paths) and media_paths[i] and media_paths[i].exists():
                media_ids = [self._upload_media(media_paths[i])]

            response = self._api.create_tweet(
                text=text[:280],
                media_ids=media_ids,
                in_reply_to_tweet_id=reply_to,
            )
            tweet_id = response.data["id"]
            tweet_ids.append(tweet_id)
            reply_to = tweet_id
            logger.info("Published thread tweet %d/%d: %s", i + 1, len(tweets), tweet_id)

        return tweet_ids

    def publish_media_tweet(self, text: str, media_path: Path) -> str:
        return self.publish_tweet(text, media_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _upload_media(self, path: Path) -> str:
        """Upload media via v1.1 API and return the media_id string."""
        media = self._api_v1.media_upload(filename=str(path))
        logger.info("Uploaded media: %s (id=%s)", path.name, media.media_id_string)
        return media.media_id_string

    def _next_media_file(self, directory: Path) -> Optional[Path]:
        if not directory.exists():
            return None
        candidates = sorted(
            (
                p for p in directory.iterdir()
                if p.is_file() and p.suffix.lower() in PHOTO_EXTENSIONS
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
            if kind == "thread":
                # Threads: split caption by double newline into tweet chunks
                chunks = [c.strip() for c in caption.split("\n\n") if c.strip()]
                if not chunks:
                    chunks = [caption]
                ids = self.publish_thread(chunks, [media_path])
                tweet_id = ids[0] if ids else None
            else:
                tweet_id = self.publish_tweet(caption, media_path)

            logger.info("Published %s (%s): %s", kind, media_path.name, tweet_id)
            _archive(media_path)
            return tweet_id

        except Exception:
            logger.exception("Failed to publish %s from %s", kind, media_path)
            return None
