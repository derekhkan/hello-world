"""Engagement module — like, retweet, and reply to posts from target
accounts and discover new relevant content via search on X (Twitter)."""

from __future__ import annotations

import json
import logging
import random
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set

logger = logging.getLogger(__name__)

FLAGGED_FILE = Path("x_flagged_accounts.json")


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
    """Automates liking, retweeting, and replying on X (Twitter)."""

    def __init__(
        self,
        api,
        target_accounts: List[str],
        discovery_keywords: List[str],
        likes_per_account: int = 3,
        replying_enabled: bool = True,
        reply_templates: Optional[List[str]] = None,
        retweet_enabled: bool = True,
        delay_min: int = 30,
        delay_max: int = 90,
    ) -> None:
        self._api = api
        self._target_accounts = target_accounts
        self._discovery_keywords = discovery_keywords
        self._likes_per_account = likes_per_account
        self._replying_enabled = replying_enabled
        self._reply_templates = reply_templates or ["Great post!"]
        self._retweet_enabled = retweet_enabled
        self._delay_min = delay_min
        self._delay_max = delay_max
        self._seen: Set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def engage_with_targets(self) -> None:
        """Like and reply to recent tweets from target accounts."""
        for username in self._target_accounts:
            try:
                self._engage_account(username)
            except Exception:
                logger.exception("Error engaging with @%s", username)

    def discover_and_engage(self) -> None:
        """Search for trending tweets by keyword and engage."""
        for keyword in self._discovery_keywords:
            try:
                self._engage_keyword(keyword)
            except Exception:
                logger.exception("Error engaging with keyword '%s'", keyword)

    def show_flagged(self) -> str:
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
            # Get user ID from username
            user_response = self._api.get_user(username=username)
            if not user_response or not user_response.data:
                _flag_account(username, "Account not found")
                return
            user_id = user_response.data.id

            # Get recent tweets
            tweets_response = self._api.get_users_tweets(
                user_id, max_results=self._likes_per_account,
                tweet_fields=["created_at"],
            )

            if not tweets_response or not tweets_response.data:
                _flag_account(username, "No recent tweets found")
                return

            for tweet in tweets_response.data:
                self._interact(tweet.id)

        except Exception as exc:
            error_msg = str(exc).lower()
            if "not found" in error_msg or "could not find" in error_msg:
                _flag_account(username, f"Account error: {exc}")
            else:
                raise

    def _engage_keyword(self, keyword: str) -> None:
        logger.info("Searching for '%s' …", keyword)

        try:
            search_response = self._api.search_recent_tweets(
                query=keyword,
                max_results=self._likes_per_account * 2,
                tweet_fields=["created_at", "author_id"],
            )

            if not search_response or not search_response.data:
                logger.info("No results for '%s'", keyword)
                return

            for tweet in search_response.data[:self._likes_per_account]:
                self._interact(tweet.id)

        except Exception:
            logger.exception("Search failed for '%s'", keyword)

    def _interact(self, tweet_id: str) -> None:
        tweet_id_str = str(tweet_id)
        if tweet_id_str in self._seen:
            return
        self._seen.add(tweet_id_str)

        # Like
        try:
            self._api.like(tweet_id)
            logger.info("Liked tweet %s", tweet_id)
        except Exception:
            logger.exception("Failed to like tweet %s", tweet_id)

        # Retweet
        if self._retweet_enabled:
            try:
                self._api.retweet(tweet_id)
                logger.info("Retweeted %s", tweet_id)
            except Exception:
                logger.exception("Failed to retweet %s", tweet_id)

        # Reply
        if self._replying_enabled:
            reply_text = random.choice(self._reply_templates)
            try:
                self._api.create_tweet(
                    text=reply_text,
                    in_reply_to_tweet_id=tweet_id,
                )
                logger.info("Replied to tweet %s: %s", tweet_id, reply_text)
            except Exception:
                logger.exception("Failed to reply to tweet %s", tweet_id)

        self._wait()

    def _wait(self) -> None:
        delay = random.uniform(self._delay_min, self._delay_max)
        logger.debug("Sleeping %.1fs …", delay)
        time.sleep(delay)
