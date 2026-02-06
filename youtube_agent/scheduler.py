"""Schedule-based orchestration for the YouTube agent."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

import schedule

from youtube_agent.client import YouTubeClient
from youtube_agent.config import AppConfig
from youtube_agent.content_calendar import CALENDAR_FILE, ContentCalendar
from youtube_agent.content_manager import ContentManager
from youtube_agent.engagement import EngagementManager

logger = logging.getLogger(__name__)


class AgentScheduler:
    """Wire up all sub-systems and run them on the configured schedule."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

        # --- YouTube session ---
        self._client = YouTubeClient(
            client_secrets_file=config.client_secrets_file,
            api_key=config.api_key,
        )
        if config.api_key and not Path(config.client_secrets_file).exists():
            self._client.login_api_key()
        else:
            self._client.login()
        api = self._client.api

        # --- Content manager ---
        self._content = ContentManager(
            api=api,
            media_dir=config.content.media_dir,
            default_tags=config.content.default_tags,
            default_category_id=config.content.default_category_id,
            default_privacy=config.content.default_privacy,
        )

        # --- Engagement manager ---
        eng = config.engagement
        self._engagement = EngagementManager(
            api=api,
            target_channels=eng.target_channels,
            discovery_keywords=eng.discovery_keywords,
            likes_per_channel=eng.likes_per_channel,
            commenting_enabled=eng.commenting_enabled,
            comment_templates=eng.comment_templates,
            delay_min=eng.delay_min,
            delay_max=eng.delay_max,
        )

        # --- Calendar ---
        self._calendar = self._load_calendar()

    # ------------------------------------------------------------------
    # Calendar helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_calendar() -> ContentCalendar | None:
        if CALENDAR_FILE.exists():
            try:
                cal = ContentCalendar.load()
                logger.info(
                    "Loaded content calendar: \"%s\" (%d entries)",
                    cal.theme, len(cal.entries),
                )
                return cal
            except Exception:
                logger.exception("Failed to load calendar file")
        return None

    def _publish_calendar_entries(self) -> None:
        if self._calendar is None:
            return

        pending = self._calendar.pending_for_today()
        now = datetime.now().strftime("%H:%M")

        for entry in pending:
            if entry.time > now:
                continue

            media_path = Path(entry.media_path)
            if not media_path.exists():
                logger.warning("Media file missing for calendar entry %s: %s", entry.id, media_path)
                continue

            try:
                if entry.content_type == "video":
                    self._content.publish_file_as_video(media_path, entry.caption)
                elif entry.content_type == "short":
                    self._content.publish_file_as_short(media_path, entry.caption)
                elif entry.content_type == "community":
                    logger.info("Community post ready: %s", entry.caption[:80])
                else:
                    logger.warning("Unknown calendar content type: %s", entry.content_type)
                    continue

                self._calendar.mark_published(entry.id)
                self._calendar.save()
                logger.info("Published calendar entry %s (%s)", entry.id, entry.content_type)

            except Exception:
                logger.exception("Failed to publish calendar entry %s", entry.id)

    # ------------------------------------------------------------------
    # Schedule registration
    # ------------------------------------------------------------------

    def _register_content_jobs(self) -> None:
        sched = self._config.content

        if sched.videos_schedule.enabled:
            for t in sched.videos_schedule.times:
                schedule.every().day.at(t).do(self._safe_run, self._content.publish_next_video)
                logger.info("Scheduled video publishing at %s", t)

        if sched.shorts_schedule.enabled:
            for t in sched.shorts_schedule.times:
                schedule.every().day.at(t).do(self._safe_run, self._content.publish_next_short)
                logger.info("Scheduled short publishing at %s", t)

        if sched.community_schedule.enabled:
            for t in sched.community_schedule.times:
                schedule.every().day.at(t).do(self._safe_run, self._content.publish_next_community_post)
                logger.info("Scheduled community post at %s", t)

    def _register_calendar_job(self) -> None:
        if self._calendar is not None:
            schedule.every(1).minutes.do(self._safe_run, self._publish_calendar_entries)
            logger.info("Scheduled calendar publisher (checks every minute)")

    def _register_engagement_jobs(self) -> None:
        if not self._config.engagement.enabled:
            return
        schedule.every(4).hours.do(self._safe_run, self._engagement.engage_with_targets)
        schedule.every(6).hours.do(self._safe_run, self._engagement.discover_and_engage)
        logger.info("Scheduled engagement jobs (targets every 4 h, discovery every 6 h)")

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run_once(self) -> None:
        logger.info("Running all YouTube jobs once …")
        self._safe_run(self._content.publish_next_video)
        self._safe_run(self._content.publish_next_short)
        self._safe_run(self._content.publish_next_community_post)
        self._safe_run(self._publish_calendar_entries)
        if self._config.engagement.enabled:
            self._safe_run(self._engagement.engage_with_targets)
            self._safe_run(self._engagement.discover_and_engage)
        logger.info("Single run complete.")

    def start(self) -> None:
        self._register_content_jobs()
        self._register_calendar_job()
        self._register_engagement_jobs()

        logger.info("YouTube agent scheduler started. Press Ctrl+C to stop.")
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Agent stopped by user.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_run(func):
        try:
            return func()
        except Exception:
            logger.exception("Job %s failed", func.__name__)
            return None
