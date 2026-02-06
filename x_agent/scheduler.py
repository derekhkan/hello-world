"""Schedule-based orchestration for the X (Twitter) agent."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

import schedule

from x_agent.client import XClient
from x_agent.config import AppConfig
from x_agent.content_calendar import CALENDAR_FILE, ContentCalendar
from x_agent.content_manager import ContentManager
from x_agent.engagement import EngagementManager

logger = logging.getLogger(__name__)


class AgentScheduler:
    """Wire up all sub-systems and run them on the configured schedule."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

        # --- X session ---
        self._client = XClient(
            api_key=config.api_key,
            api_secret=config.api_secret,
            access_token=config.access_token,
            access_token_secret=config.access_token_secret,
            bearer_token=config.bearer_token,
        )
        self._client.login()

        # --- Content manager ---
        self._content = ContentManager(
            api=self._client.api,
            api_v1=self._client.api_v1,
            media_dir=config.content.media_dir,
            default_hashtags=config.content.default_hashtags,
        )

        # --- Engagement manager ---
        eng = config.engagement
        self._engagement = EngagementManager(
            api=self._client.api,
            target_accounts=eng.target_accounts,
            discovery_keywords=eng.discovery_keywords,
            likes_per_account=eng.likes_per_account,
            replying_enabled=eng.replying_enabled,
            reply_templates=eng.reply_templates,
            retweet_enabled=eng.retweet_enabled,
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
                if entry.content_type == "tweet":
                    self._content.publish_tweet(entry.caption, media_path)
                elif entry.content_type == "thread":
                    chunks = [c.strip() for c in entry.caption.split("\n\n") if c.strip()]
                    self._content.publish_thread(chunks, [media_path] if media_path else None)
                elif entry.content_type == "media_post":
                    if media_path and media_path.exists():
                        self._content.publish_media_tweet(entry.caption, media_path)
                    else:
                        self._content.publish_tweet(entry.caption)
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

        if sched.tweets_schedule.enabled:
            for t in sched.tweets_schedule.times:
                schedule.every().day.at(t).do(self._safe_run, self._content.publish_next_tweet)
                logger.info("Scheduled tweet publishing at %s", t)

        if sched.threads_schedule.enabled:
            for t in sched.threads_schedule.times:
                schedule.every().day.at(t).do(self._safe_run, self._content.publish_next_thread)
                logger.info("Scheduled thread publishing at %s", t)

        if sched.media_posts_schedule.enabled:
            for t in sched.media_posts_schedule.times:
                schedule.every().day.at(t).do(self._safe_run, self._content.publish_next_media_post)
                logger.info("Scheduled media post at %s", t)

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
        logger.info("Running all X jobs once …")
        self._safe_run(self._content.publish_next_tweet)
        self._safe_run(self._content.publish_next_thread)
        self._safe_run(self._content.publish_next_media_post)
        self._safe_run(self._publish_calendar_entries)
        if self._config.engagement.enabled:
            self._safe_run(self._engagement.engage_with_targets)
            self._safe_run(self._engagement.discover_and_engage)
        logger.info("Single run complete.")

    def start(self) -> None:
        self._register_content_jobs()
        self._register_calendar_job()
        self._register_engagement_jobs()

        logger.info("X agent scheduler started. Press Ctrl+C to stop.")
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
