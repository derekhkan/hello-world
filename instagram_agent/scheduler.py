"""Schedule-based orchestration — ties content publishing and engagement
together and runs them on a configurable timetable."""

from __future__ import annotations

import logging
import time

import schedule

from instagram_agent.client import InstagramClient
from instagram_agent.config import AppConfig
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

    # ------------------------------------------------------------------
    # Schedule registration
    # ------------------------------------------------------------------

    def _register_content_jobs(self) -> None:
        """Register content-publishing jobs based on the config schedule."""
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

    def _register_engagement_jobs(self) -> None:
        """Run engagement once every 4 hours."""
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
        if self._config.engagement.enabled:
            self._safe_run(self._engagement.engage_with_targets)
            self._safe_run(self._engagement.discover_and_engage)
        logger.info("Single run complete.")

    def start(self) -> None:
        """Register all jobs and enter the infinite scheduling loop."""
        self._register_content_jobs()
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
        """Call *func*, catching and logging any exception so one failure
        doesn't crash the whole scheduler."""
        try:
            return func()
        except Exception:
            logger.exception("Job %s failed", func.__name__)
            return None
