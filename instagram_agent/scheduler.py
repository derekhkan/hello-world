"""Schedule-based orchestration — ties content publishing, calendar-driven
posting, and engagement together and runs them on a configurable timetable."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

import schedule

from instagram_agent.client import InstagramClient
from instagram_agent.config import AppConfig
from instagram_agent.content_calendar import CALENDAR_FILE, ContentCalendar
from instagram_agent.content_manager import ContentManager
from instagram_agent.engagement import EngagementManager

logger = logging.getLogger(__name__)


class AgentScheduler:
    """Wire up all sub-systems and run them on the configured schedule."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

        # --- Instagram session ---
        self._client = InstagramClient(config.username, config.password)
        self._client.login()
        api = self._client.api

        # --- Content manager ---
        self._content = ContentManager(
            api=api,
            media_dir=config.content.media_dir,
            default_hashtags=config.content.default_hashtags,
        )

        # --- Engagement manager ---
        eng = config.engagement
        self._engagement = EngagementManager(
            api=api,
            target_accounts=eng.target_accounts,
            discovery_hashtags=eng.discovery_hashtags,
            likes_per_account=eng.likes_per_account,
            commenting_enabled=eng.commenting_enabled,
            comment_templates=eng.comment_templates,
            delay_min=eng.delay_min,
            delay_max=eng.delay_max,
        )

        # --- Calendar (loaded if exists) ---
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
                    cal.theme,
                    len(cal.entries),
                )
                return cal
            except Exception:
                logger.exception("Failed to load calendar file")
        return None

    def _publish_calendar_entries(self) -> None:
        """Check the calendar for entries due right now and publish them."""
        if self._calendar is None:
            return

        pending = self._calendar.pending_for_today()
        now = datetime.now().strftime("%H:%M")

        for entry in pending:
            if entry.time > now:
                continue  # not yet time

            media_path = Path(entry.media_path)
            if not media_path.exists():
                logger.warning("Media file missing for calendar entry %s: %s", entry.id, media_path)
                continue

            try:
                if entry.content_type == "post":
                    self._content.publish_file_as_post(media_path, entry.caption)
                elif entry.content_type == "reel":
                    self._content.publish_file_as_reel(media_path, entry.caption)
                elif entry.content_type == "story":
                    self._content.publish_file_as_story(media_path)
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

        if sched.posts_schedule.enabled:
            for t in sched.posts_schedule.times:
                schedule.every().day.at(t).do(self._safe_run, self._content.publish_next_post)
                logger.info("Scheduled post publishing at %s", t)

        if sched.reels_schedule.enabled:
            for t in sched.reels_schedule.times:
                schedule.every().day.at(t).do(self._safe_run, self._content.publish_next_reel)
                logger.info("Scheduled reel publishing at %s", t)

        if sched.stories_schedule.enabled:
            for t in sched.stories_schedule.times:
                schedule.every().day.at(t).do(self._safe_run, self._content.publish_next_story)
                logger.info("Scheduled story publishing at %s", t)

    def _register_calendar_job(self) -> None:
        """Check the calendar every minute for entries that are due."""
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
        """Execute every registered job immediately (useful for testing)."""
        logger.info("Running all jobs once …")
        self._safe_run(self._content.publish_next_post)
        self._safe_run(self._content.publish_next_reel)
        self._safe_run(self._content.publish_next_story)
        self._safe_run(self._publish_calendar_entries)
        if self._config.engagement.enabled:
            self._safe_run(self._engagement.engage_with_targets)
            self._safe_run(self._engagement.discover_and_engage)
        logger.info("Single run complete.")

    def start(self) -> None:
        """Register all jobs and enter the infinite scheduling loop."""
        self._register_content_jobs()
        self._register_calendar_job()
        self._register_engagement_jobs()

        logger.info("Agent scheduler started. Press Ctrl+C to stop.")
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
