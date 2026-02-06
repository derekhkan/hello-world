"""Schedule-based orchestration for the LinkedIn agent."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

import schedule

from linkedin_agent.client import LinkedInClient
from linkedin_agent.config import AppConfig
from linkedin_agent.content_calendar import CALENDAR_FILE, ContentCalendar
from linkedin_agent.content_manager import ContentManager
from linkedin_agent.engagement import EngagementManager

logger = logging.getLogger(__name__)


class AgentScheduler:
    """Wire up all sub-systems and run them on the configured schedule."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

        # --- LinkedIn session ---
        self._client = LinkedInClient(
            access_token=config.access_token,
            person_urn=config.person_urn or None,
        )
        self._client.login()

        # --- Content manager ---
        self._content = ContentManager(
            session=self._client.session,
            person_urn=self._client.person_urn,
            media_dir=config.content.media_dir,
            default_hashtags=config.content.default_hashtags,
        )

        # --- Engagement manager ---
        eng = config.engagement
        self._engagement = EngagementManager(
            session=self._client.session,
            person_urn=self._client.person_urn,
            target_authors=eng.target_authors,
            discovery_keywords=eng.discovery_keywords,
            likes_per_author=eng.likes_per_author,
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

            media_path = Path(entry.media_path) if entry.media_path else None

            try:
                if entry.content_type in ("post", "carousel"):
                    if media_path and media_path.exists():
                        self._content.publish_image_post(entry.caption, media_path)
                    else:
                        self._content.publish_text_post(entry.caption)
                elif entry.content_type == "article":
                    self._content.publish_text_post(entry.caption)
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

        if sched.articles_schedule.enabled:
            for t in sched.articles_schedule.times:
                schedule.every().day.at(t).do(self._safe_run, self._content.publish_next_article)
                logger.info("Scheduled article publishing at %s", t)

        if sched.carousels_schedule.enabled:
            for t in sched.carousels_schedule.times:
                schedule.every().day.at(t).do(self._safe_run, self._content.publish_next_carousel)
                logger.info("Scheduled carousel publishing at %s", t)

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
        logger.info("Running all LinkedIn jobs once …")
        self._safe_run(self._content.publish_next_post)
        self._safe_run(self._content.publish_next_article)
        self._safe_run(self._content.publish_next_carousel)
        self._safe_run(self._publish_calendar_entries)
        if self._config.engagement.enabled:
            self._safe_run(self._engagement.engage_with_targets)
            self._safe_run(self._engagement.discover_and_engage)
        logger.info("Single run complete.")

    def start(self) -> None:
        self._register_content_jobs()
        self._register_calendar_job()
        self._register_engagement_jobs()

        logger.info("LinkedIn agent scheduler started. Press Ctrl+C to stop.")
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
