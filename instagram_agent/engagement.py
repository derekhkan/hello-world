"""Engagement module — like and comment on posts from target accounts and
discover new relevant accounts via hashtag exploration."""

from __future__ import annotations

import logging
import random
import time
from typing import List, Optional, Set

from instagrapi import Client
from instagrapi.types import Media, User

logger = logging.getLogger(__name__)


class EngagementManager:
    """Automates liking and commenting on relevant accounts' posts."""

    def __init__(
        self,
        api: Client,
        target_accounts: List[str],
        discovery_hashtags: List[str],
        likes_per_account: int = 3,
        commenting_enabled: bool = True,
        comment_templates: Optional[List[str]] = None,
        delay_min: int = 30,
        delay_max: int = 90,
    ) -> None:
        self._api = api
        self._target_accounts = target_accounts
        self._discovery_hashtags = discovery_hashtags
        self._likes_per_account = likes_per_account
        self._commenting_enabled = commenting_enabled
        self._comment_templates = comment_templates or ["Great post!"]
        self._delay_min = delay_min
        self._delay_max = delay_max
        # Keep track of media we've already interacted with during this run
        self._seen: Set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def engage_with_targets(self) -> None:
        """Like (and optionally comment on) recent posts of every target
        account."""
        for username in self._target_accounts:
            try:
                self._engage_account(username)
            except Exception:
                logger.exception(
                    "Error engaging with account %s", username
                )

    def discover_and_engage(self) -> None:
        """Find recent top posts for each discovery hashtag, like them, and
        optionally comment."""
        for tag in self._discovery_hashtags:
            try:
                self._engage_hashtag(tag)
            except Exception:
                logger.exception("Error engaging with hashtag #%s", tag)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _engage_account(self, username: str) -> None:
        logger.info("Engaging with @%s …", username)
        user_id = self._api.user_id_from_username(username)
        medias: List[Media] = self._api.user_medias(
            user_id, amount=self._likes_per_account
        )
        for media in medias:
            self._interact(media)

    def _engage_hashtag(self, tag: str) -> None:
        logger.info("Exploring #%s …", tag)
        medias: List[Media] = self._api.hashtag_medias_top(
            tag, amount=self._likes_per_account
        )
        for media in medias:
            self._interact(media)

    def _interact(self, media: Media) -> None:
        media_pk = str(media.pk)
        if media_pk in self._seen:
            return
        self._seen.add(media_pk)

        # Like
        try:
            self._api.media_like(media.id)
            logger.info("Liked media %s by @%s", media.pk, media.user.username)
        except Exception:
            logger.exception("Failed to like media %s", media.pk)

        # Comment
        if self._commenting_enabled:
            comment_text = random.choice(self._comment_templates)
            try:
                self._api.media_comment(media.id, comment_text)
                logger.info(
                    "Commented on media %s: %s", media.pk, comment_text
                )
            except Exception:
                logger.exception("Failed to comment on media %s", media.pk)

        # Rate-limit pause
        self._wait()

    def _wait(self) -> None:
        delay = random.uniform(self._delay_min, self._delay_max)
        logger.debug("Sleeping %.1fs …", delay)
        time.sleep(delay)
