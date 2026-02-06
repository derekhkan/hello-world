"""Engagement module — like and comment on posts from target accounts and
discover new relevant accounts via hashtag exploration.

Accounts that can't be found (renamed, deactivated, etc.) are flagged in
``flagged_accounts.json`` so they can be cleaned up at the end of the week.
"""

from __future__ import annotations

import json
import logging
import random
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set

from instagrapi import Client
from instagrapi.exceptions import (
    ChallengeRequired,
    ClientError,
    UserNotFound,
)
from instagrapi.types import Media, User

logger = logging.getLogger(__name__)

FLAGGED_FILE = Path("flagged_accounts.json")


# ---------------------------------------------------------------------------
# Flagged-account tracker
# ---------------------------------------------------------------------------

def _load_flagged() -> dict:
    if FLAGGED_FILE.exists():
        with open(FLAGGED_FILE) as fh:
            return json.load(fh)
    return {}


def _save_flagged(data: dict) -> None:
    with open(FLAGGED_FILE, "w") as fh:
        json.dump(data, fh, indent=2)


def _flag_account(username: str, reason: str) -> None:
    flagged = _load_flagged()
    flagged[username] = {
        "reason": reason,
        "flagged_at": datetime.now().isoformat(),
    }
    _save_flagged(flagged)
    logger.warning("Flagged @%s: %s", username, reason)


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
        self._seen: Set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def engage_with_targets(self) -> None:
        """Like (and optionally comment on) recent posts of every target
        account.  Skips and flags accounts that can't be found."""
        for username in self._target_accounts:
            try:
                self._engage_account(username)
            except UserNotFound:
                _flag_account(username, "Account not found (renamed or deleted)")
            except ClientError as exc:
                error_msg = str(exc).lower()
                if "not found" in error_msg or "user" in error_msg:
                    _flag_account(username, f"Client error: {exc}")
                else:
                    logger.exception("Error engaging with @%s", username)
            except ChallengeRequired:
                logger.error("Challenge required — stopping engagement to avoid further blocks")
                return
            except Exception:
                logger.exception("Unexpected error engaging with @%s", username)

    def discover_and_engage(self) -> None:
        """Find recent top posts for each discovery hashtag, like them, and
        optionally comment."""
        for tag in self._discovery_hashtags:
            try:
                self._engage_hashtag(tag)
            except ChallengeRequired:
                logger.error("Challenge required — stopping discovery to avoid further blocks")
                return
            except Exception:
                logger.exception("Error engaging with hashtag #%s", tag)

    def show_flagged(self) -> str:
        """Return a human-readable summary of all flagged accounts."""
        flagged = _load_flagged()
        if not flagged:
            return "No flagged accounts."
        lines = ["Flagged accounts:", ""]
        for username, info in flagged.items():
            lines.append(f"  @{username}")
            lines.append(f"    Reason:  {info['reason']}")
            lines.append(f"    Flagged: {info['flagged_at']}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def clear_flagged() -> int:
        """Remove the flagged-accounts file. Returns count of cleared entries."""
        flagged = _load_flagged()
        count = len(flagged)
        if FLAGGED_FILE.exists():
            FLAGGED_FILE.unlink()
        return count

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _engage_account(self, username: str) -> None:
        logger.info("Engaging with @%s …", username)
        try:
            user_id = self._api.user_id_from_username(username)
        except Exception as exc:
            error_msg = str(exc).lower()
            if "not found" in error_msg or "does not exist" in error_msg:
                _flag_account(username, "Account not found (renamed or deleted)")
                return
            raise

        try:
            medias: List[Media] = self._api.user_medias(
                user_id, amount=self._likes_per_account
            )
        except Exception as exc:
            error_msg = str(exc).lower()
            if "private" in error_msg or "not accessible" in error_msg:
                _flag_account(username, "Account is private or not accessible")
                return
            raise

        if not medias:
            _flag_account(username, "No recent posts found (may be inactive)")
            return

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
        except ChallengeRequired:
            logger.error("Challenge required on like — stopping")
            raise
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
            except ChallengeRequired:
                logger.error("Challenge required on comment — stopping")
                raise
            except Exception:
                logger.exception("Failed to comment on media %s", media.pk)

        self._wait()

    def _wait(self) -> None:
        delay = random.uniform(self._delay_min, self._delay_max)
        logger.debug("Sleeping %.1fs …", delay)
        time.sleep(delay)
