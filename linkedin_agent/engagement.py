"""Engagement module — like and comment on posts from connections and
discover relevant content via LinkedIn feed and hashtags."""

from __future__ import annotations

import json
import logging
import random
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set

import requests

logger = logging.getLogger(__name__)

FLAGGED_FILE = Path("li_flagged_profiles.json")
API_BASE = "https://api.linkedin.com/v2"


# ---------------------------------------------------------------------------
# Flagged-profile tracker
# ---------------------------------------------------------------------------

def _load_flagged() -> dict:
    if FLAGGED_FILE.exists():
        with open(FLAGGED_FILE) as fh:
            return json.load(fh)
    return {}


def _save_flagged(data: dict) -> None:
    with open(FLAGGED_FILE, "w") as fh:
        json.dump(data, fh, indent=2)


def _flag_profile(profile_id: str, reason: str) -> None:
    flagged = _load_flagged()
    flagged[profile_id] = {
        "reason": reason,
        "flagged_at": datetime.now().isoformat(),
    }
    _save_flagged(flagged)
    logger.warning("Flagged profile %s: %s", profile_id, reason)


class EngagementManager:
    """Automates liking and commenting on relevant LinkedIn posts."""

    def __init__(
        self,
        session: requests.Session,
        person_urn: str,
        target_authors: List[str],
        discovery_keywords: List[str],
        likes_per_author: int = 3,
        commenting_enabled: bool = True,
        comment_templates: Optional[List[str]] = None,
        delay_min: int = 60,
        delay_max: int = 180,
    ) -> None:
        self._session = session
        self._person_urn = person_urn
        self._target_authors = target_authors
        self._discovery_keywords = discovery_keywords
        self._likes_per_author = likes_per_author
        self._commenting_enabled = commenting_enabled
        self._comment_templates = comment_templates or [
            "Great insight! Thanks for sharing."
        ]
        self._delay_min = delay_min
        self._delay_max = delay_max
        self._seen: Set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def engage_with_targets(self) -> None:
        """Like and comment on posts from target author URNs."""
        for author_urn in self._target_authors:
            try:
                self._engage_author(author_urn)
            except Exception:
                logger.exception("Error engaging with %s", author_urn)

    def discover_and_engage(self) -> None:
        """LinkedIn doesn't have a public search API for posts, so
        this method logs the intent. For full discovery, consider using
        LinkedIn's Sales Navigator API or manual feed scanning."""
        for keyword in self._discovery_keywords:
            logger.info(
                "Discovery keyword '%s' noted — LinkedIn post search "
                "requires Sales Navigator API or manual feed review.",
                keyword,
            )

    def show_flagged(self) -> str:
        flagged = _load_flagged()
        if not flagged:
            return "No flagged profiles."
        lines = ["Flagged profiles:", ""]
        for profile_id, info in flagged.items():
            lines.append(f"  {profile_id}")
            lines.append(f"    Reason:  {info['reason']}")
            lines.append(f"    Flagged: {info['flagged_at']}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def clear_flagged() -> int:
        flagged = _load_flagged()
        count = len(flagged)
        if FLAGGED_FILE.exists():
            FLAGGED_FILE.unlink()
        return count

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _engage_author(self, author_urn: str) -> None:
        """Engage with recent posts from a specific author.

        Note: LinkedIn's API for fetching posts by author is limited.
        This uses the UGC posts endpoint which requires appropriate
        API permissions.
        """
        logger.info("Engaging with author %s …", author_urn)

        try:
            resp = self._session.get(
                f"{API_BASE}/ugcPosts",
                params={
                    "q": "authors",
                    "authors": f"List({author_urn})",
                    "count": self._likes_per_author,
                },
            )
            resp.raise_for_status()
            posts = resp.json().get("elements", [])

            if not posts:
                _flag_profile(author_urn, "No recent posts found")
                return

            for post in posts[:self._likes_per_author]:
                post_urn = post.get("id", "")
                if post_urn:
                    self._interact(post_urn)

        except requests.HTTPError as exc:
            if exc.response and exc.response.status_code == 404:
                _flag_profile(author_urn, "Author not found")
            else:
                raise

    def _interact(self, post_urn: str) -> None:
        if post_urn in self._seen:
            return
        self._seen.add(post_urn)

        # Like (social action)
        try:
            like_body = {
                "actor": self._person_urn,
                "object": post_urn,
            }
            resp = self._session.post(
                f"{API_BASE}/socialActions/{post_urn}/likes",
                json=like_body,
            )
            resp.raise_for_status()
            logger.info("Liked post %s", post_urn)
        except Exception:
            logger.exception("Failed to like post %s", post_urn)

        # Comment
        if self._commenting_enabled:
            comment_text = random.choice(self._comment_templates)
            try:
                comment_body = {
                    "actor": self._person_urn,
                    "object": post_urn,
                    "message": {
                        "text": comment_text,
                    },
                }
                resp = self._session.post(
                    f"{API_BASE}/socialActions/{post_urn}/comments",
                    json=comment_body,
                )
                resp.raise_for_status()
                logger.info("Commented on post %s: %s", post_urn, comment_text)
            except Exception:
                logger.exception("Failed to comment on post %s", post_urn)

        self._wait()

    def _wait(self) -> None:
        delay = random.uniform(self._delay_min, self._delay_max)
        logger.debug("Sleeping %.1fs …", delay)
        time.sleep(delay)
