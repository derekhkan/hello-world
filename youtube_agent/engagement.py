"""Engagement module — like and comment on videos from target channels and
discover new relevant content via search."""

from __future__ import annotations

import json
import logging
import random
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set

logger = logging.getLogger(__name__)

FLAGGED_FILE = Path("yt_flagged_channels.json")


# ---------------------------------------------------------------------------
# Flagged-channel tracker
# ---------------------------------------------------------------------------

def _load_flagged() -> dict:
    if FLAGGED_FILE.exists():
        with open(FLAGGED_FILE) as fh:
            return json.load(fh)
    return {}


def _save_flagged(data: dict) -> None:
    with open(FLAGGED_FILE, "w") as fh:
        json.dump(data, fh, indent=2)


def _flag_channel(channel_id: str, reason: str) -> None:
    flagged = _load_flagged()
    flagged[channel_id] = {
        "reason": reason,
        "flagged_at": datetime.now().isoformat(),
    }
    _save_flagged(flagged)
    logger.warning("Flagged channel %s: %s", channel_id, reason)


class EngagementManager:
    """Automates liking and commenting on relevant YouTube videos."""

    def __init__(
        self,
        api,
        target_channels: List[str],
        discovery_keywords: List[str],
        likes_per_channel: int = 3,
        commenting_enabled: bool = True,
        comment_templates: Optional[List[str]] = None,
        delay_min: int = 30,
        delay_max: int = 90,
    ) -> None:
        self._api = api
        self._target_channels = target_channels
        self._discovery_keywords = discovery_keywords
        self._likes_per_channel = likes_per_channel
        self._commenting_enabled = commenting_enabled
        self._comment_templates = comment_templates or ["Great video!"]
        self._delay_min = delay_min
        self._delay_max = delay_max
        self._seen: Set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def engage_with_targets(self) -> None:
        """Like and comment on recent videos from target channels."""
        for channel_id in self._target_channels:
            try:
                self._engage_channel(channel_id)
            except Exception:
                logger.exception("Error engaging with channel %s", channel_id)

    def discover_and_engage(self) -> None:
        """Search for trending videos by keyword and engage with them."""
        for keyword in self._discovery_keywords:
            try:
                self._engage_keyword(keyword)
            except Exception:
                logger.exception("Error engaging with keyword '%s'", keyword)

    def show_flagged(self) -> str:
        flagged = _load_flagged()
        if not flagged:
            return "No flagged channels."
        lines = ["Flagged channels:", ""]
        for channel_id, info in flagged.items():
            lines.append(f"  {channel_id}")
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

    def _engage_channel(self, channel_id: str) -> None:
        logger.info("Engaging with channel %s …", channel_id)

        try:
            # Get recent uploads from channel
            channels_response = self._api.channels().list(
                part="contentDetails", id=channel_id
            ).execute()

            items = channels_response.get("items", [])
            if not items:
                _flag_channel(channel_id, "Channel not found")
                return

            uploads_playlist = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

            playlist_response = self._api.playlistItems().list(
                part="snippet",
                playlistId=uploads_playlist,
                maxResults=self._likes_per_channel,
            ).execute()

            for item in playlist_response.get("items", []):
                video_id = item["snippet"]["resourceId"]["videoId"]
                self._interact(video_id)

        except Exception as exc:
            error_msg = str(exc).lower()
            if "not found" in error_msg:
                _flag_channel(channel_id, "Channel not found")
            else:
                raise

    def _engage_keyword(self, keyword: str) -> None:
        logger.info("Searching for '%s' …", keyword)

        search_response = self._api.search().list(
            q=keyword,
            part="id",
            type="video",
            order="relevance",
            maxResults=self._likes_per_channel,
        ).execute()

        for item in search_response.get("items", []):
            video_id = item["id"]["videoId"]
            self._interact(video_id)

    def _interact(self, video_id: str) -> None:
        if video_id in self._seen:
            return
        self._seen.add(video_id)

        # Like
        try:
            self._api.videos().rate(id=video_id, rating="like").execute()
            logger.info("Liked video %s", video_id)
        except Exception:
            logger.exception("Failed to like video %s", video_id)

        # Comment
        if self._commenting_enabled:
            comment_text = random.choice(self._comment_templates)
            try:
                self._api.commentThreads().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "videoId": video_id,
                            "topLevelComment": {
                                "snippet": {
                                    "textOriginal": comment_text,
                                }
                            },
                        }
                    },
                ).execute()
                logger.info("Commented on video %s: %s", video_id, comment_text)
            except Exception:
                logger.exception("Failed to comment on video %s", video_id)

        self._wait()

    def _wait(self) -> None:
        delay = random.uniform(self._delay_min, self._delay_max)
        logger.debug("Sleeping %.1fs …", delay)
        time.sleep(delay)
