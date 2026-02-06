"""Brand kit — download existing posts from your Instagram account and
save them locally for use as backgrounds in generated content.

Usage::

    python main.py brand-kit --count 30

This downloads your most recent posts into ``media/brand_kit/`` so the
content generator can use your real photos as backgrounds instead of
plain coloured rectangles.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional

from instagrapi import Client
from instagrapi.types import Media

logger = logging.getLogger(__name__)

BRAND_KIT_DIR = Path("media/brand_kit")


class BrandKitDownloader:
    """Pull existing photos from your own Instagram account."""

    def __init__(self, api: Client, media_dir: str | Path = "./media") -> None:
        self._api = api
        self._kit_dir = Path(media_dir) / "brand_kit"

    def download(self, username: str, count: int = 30) -> list[Path]:
        """Download the most recent *count* photo posts from *username*.

        Returns a list of saved file paths.
        """
        self._kit_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Fetching user ID for @%s …", username)
        user_id = self._api.user_id_from_username(username)

        logger.info("Downloading up to %d posts from @%s …", count, username)
        medias = self._api.user_medias(user_id, amount=count)

        saved: list[Path] = []
        for media in medias:
            path = self._download_media(media)
            if path is not None:
                saved.append(path)

        logger.info("Downloaded %d images to %s", len(saved), self._kit_dir)
        return saved

    def _download_media(self, media: Media) -> Optional[Path]:
        """Download a single media item (photo only — skip videos/carousels
        for the brand kit since we use these as static backgrounds)."""
        # Only grab single photos (media_type 1) and the first image of
        # carousels (media_type 8)
        try:
            if media.media_type == 1 and media.thumbnail_url:
                return self._save_photo(media)
            elif media.media_type == 8 and media.resources:
                # Carousel — grab the first image
                first = media.resources[0]
                if first.thumbnail_url:
                    return self._save_resource(media, first)
        except Exception:
            logger.exception("Failed to download media %s", media.pk)
        return None

    def _save_photo(self, media: Media) -> Path:
        dest = self._kit_dir / f"{media.pk}.jpg"
        if dest.exists():
            logger.debug("Already have %s", dest.name)
            return dest
        path = self._api.photo_download(media.pk, self._kit_dir)
        # instagrapi may save with a different name; rename to pk.jpg
        if path and Path(path).exists() and Path(path) != dest:
            shutil.move(str(path), str(dest))
        logger.info("Saved %s", dest.name)
        return dest

    def _save_resource(self, media: Media, resource, ) -> Path:
        dest = self._kit_dir / f"{media.pk}_0.jpg"
        if dest.exists():
            return dest
        path = self._api.photo_download(media.pk, self._kit_dir)
        if path and Path(path).exists() and Path(path) != dest:
            shutil.move(str(path), str(dest))
        logger.info("Saved %s (carousel)", dest.name)
        return dest

    def list_kit(self) -> list[Path]:
        """Return all images currently in the brand kit."""
        if not self._kit_dir.exists():
            return []
        return sorted(
            p for p in self._kit_dir.iterdir()
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}
        )

    @property
    def kit_dir(self) -> Path:
        return self._kit_dir
