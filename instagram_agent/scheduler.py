"""Schedule-based orchestration — ties content publishing, calendar-driven
posting, and engagement together and runs them on a configurable timetable.

Supports two publishing backends:
1. **Graph API** (preferred) — uses Meta's official API, no challenge errors
2. **instagrapi** (fallback) — private API, used for engagement (likes/comments)
"""

from __future__ import annotations

import logging
import shutil
import time
from datetime import datetime
from pathlib import Path

import schedule

from instagram_agent.config import AppConfig
from instagram_agent.content_calendar import CALENDAR_FILE, ContentCalendar

logger = logging.getLogger(__name__)

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}
VIDEO_EXTENSIONS = {".mp4", ".mov"}


def _archive(media_path: Path) -> None:
    """Move a published file into an ``archive/`` subdirectory."""
    archive_dir = media_path.parent / "archive"
    archive_dir.mkdir(exist_ok=True)
    dest = archive_dir / media_path.name
    shutil.move(str(media_path), str(dest))
    sidecar = media_path.with_suffix(".txt")
    if sidecar.exists():
        shutil.move(str(sidecar), str(archive_dir / sidecar.name))
    logger.info("Archived %s", media_path.name)


class AgentScheduler:
    """Wire up all sub-systems and run them on the configured schedule."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._graph = None
        self._content = None
        self._engagement = None

        # --- Prefer Graph API for publishing ---
        if config.graph_api_token and config.instagram_account_id:
            from instagram_agent.graph_api_client import GraphAPIClient
            self._graph = GraphAPIClient(
                access_token=config.graph_api_token,
                instagram_account_id=config.instagram_account_id,
                facebook_page_id=config.facebook_page_id,
            )
            try:
                info = self._graph.verify()
                logger.info(
                    "Graph API connected: %s",
                    info.get("username", info.get("id")),
                )
            except Exception as e:
                logger.warning("Graph API verification failed: %s", e)
                logger.warning("Falling back to instagrapi")
                self._graph = None

        # --- instagrapi (for engagement, or publishing fallback) ---
        if self._graph is None or config.engagement.enabled:
            try:
                from instagram_agent.client import InstagramClient
                from instagram_agent.content_manager import ContentManager
                self._insta_client = InstagramClient(config.username, config.password)
                self._insta_client.login()
                api = self._insta_client.api

                self._content = ContentManager(
                    api=api,
                    media_dir=config.content.media_dir,
                    default_hashtags=config.content.default_hashtags,
                )

                if config.engagement.enabled:
                    from instagram_agent.engagement import EngagementManager
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
            except Exception as e:
                logger.warning("instagrapi login failed: %s", e)
                if self._graph is None:
                    raise

        # --- Calendar (loaded if exists) ---
        self._calendar = self._load_calendar()

    # ------------------------------------------------------------------
    # Publishing (Graph API preferred, instagrapi fallback)
    # ------------------------------------------------------------------

    def _publish_post(self, path: Path, caption: str) -> None:
        """Publish a post using the best available backend."""
        hashtags = self._config.content.default_hashtags
        if hashtags:
            caption = f"{caption}\n\n{' '.join(hashtags)}"

        if self._graph:
            self._graph.publish_photo(path, caption)
        elif self._content:
            self._content.publish_file_as_post(path, caption)
        else:
            raise Exception("No publishing backend available")

    def _publish_reel(self, path: Path, caption: str) -> None:
        """Publish a reel using the best available backend."""
        hashtags = self._config.content.default_hashtags
        if hashtags:
            caption = f"{caption}\n\n{' '.join(hashtags)}"

        if self._graph:
            self._graph.publish_reel(path, caption)
        elif self._content:
            self._content.publish_file_as_reel(path, caption)
        else:
            raise Exception("No publishing backend available")

    def _publish_story(self, path: Path) -> None:
        """Publish a story using the best available backend."""
        if self._graph:
            self._graph.publish_story(path)
        elif self._content:
            self._content.publish_file_as_story(path)
        else:
            raise Exception("No publishing backend available")

    # ------------------------------------------------------------------
    # Queue-based publishing (oldest un-archived file in directory)
    # ------------------------------------------------------------------

    def _publish_next_from_dir(self, directory: Path, kind: str) -> None:
        """Publish the oldest media file in a directory."""
        if not directory.exists():
            return
        candidates = sorted(
            (
                p for p in directory.iterdir()
                if p.is_file()
                and p.suffix.lower() in PHOTO_EXTENSIONS | VIDEO_EXTENSIONS
            ),
            key=lambda p: p.stat().st_mtime,
        )
        if not candidates:
            logger.info("No queued %s media in %s", kind, directory)
            return

        media_path = candidates[0]
        caption = self._read_caption(media_path)

        try:
            if kind == "post":
                self._publish_post(media_path, caption)
            elif kind == "reel":
                self._publish_reel(media_path, caption)
            elif kind == "story":
                self._publish_story(media_path)
            _archive(media_path)
        except Exception:
            logger.exception("Failed to publish %s from %s", kind, media_path)

    def _read_caption(self, media_path: Path) -> str:
        sidecar = media_path.with_suffix(".txt")
        if sidecar.exists():
            return sidecar.read_text().strip()
        generic = media_path.parent / "caption.txt"
        if generic.exists():
            return generic.read_text().strip()
        return ""

    def _publish_next_post(self) -> None:
        self._publish_next_from_dir(
            Path(self._config.content.media_dir) / "posts", "post"
        )

    def _publish_next_reel(self) -> None:
        self._publish_next_from_dir(
            Path(self._config.content.media_dir) / "reels", "reel"
        )

    def _publish_next_story(self) -> None:
        self._publish_next_from_dir(
            Path(self._config.content.media_dir) / "stories", "story"
        )

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
                continue

            media_path = Path(entry.media_path)
            if not media_path.exists():
                logger.warning(
                    "Media file missing for calendar entry %s: %s",
                    entry.id, media_path,
                )
                continue

            try:
                if entry.content_type == "post":
                    self._publish_post(media_path, entry.caption)
                elif entry.content_type == "reel":
                    self._publish_reel(media_path, entry.caption)
                elif entry.content_type == "story":
                    self._publish_story(media_path)
                else:
                    logger.warning("Unknown content type: %s", entry.content_type)
                    continue

                self._calendar.mark_published(entry.id)
                self._calendar.save()
                logger.info(
                    "Published calendar entry %s (%s) via %s",
                    entry.id,
                    entry.content_type,
                    "Graph API" if self._graph else "instagrapi",
                )

            except Exception:
                logger.exception("Failed to publish calendar entry %s", entry.id)

    # ------------------------------------------------------------------
    # Schedule registration
    # ------------------------------------------------------------------

    def _register_content_jobs(self) -> None:
        sched = self._config.content

        if sched.posts_schedule.enabled:
            for t in sched.posts_schedule.times:
                schedule.every().day.at(t).do(self._safe_run, self._publish_next_post)
                logger.info("Scheduled post publishing at %s", t)

        if sched.reels_schedule.enabled:
            for t in sched.reels_schedule.times:
                schedule.every().day.at(t).do(self._safe_run, self._publish_next_reel)
                logger.info("Scheduled reel publishing at %s", t)

        if sched.stories_schedule.enabled:
            for t in sched.stories_schedule.times:
                schedule.every().day.at(t).do(self._safe_run, self._publish_next_story)
                logger.info("Scheduled story publishing at %s", t)

    def _register_calendar_job(self) -> None:
        if self._calendar is not None:
            schedule.every(1).minutes.do(
                self._safe_run, self._publish_calendar_entries
            )
            logger.info("Scheduled calendar publisher (checks every minute)")

    def _register_engagement_jobs(self) -> None:
        if not self._config.engagement.enabled or self._engagement is None:
            return
        schedule.every(4).hours.do(
            self._safe_run, self._engagement.engage_with_targets
        )
        schedule.every(6).hours.do(
            self._safe_run, self._engagement.discover_and_engage
        )
        logger.info("Scheduled engagement jobs (targets every 4h, discovery every 6h)")

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run_once(self) -> None:
        """Execute every registered job immediately (useful for testing)."""
        logger.info(
            "Running all jobs once (publishing via %s) …",
            "Graph API" if self._graph else "instagrapi",
        )
        self._safe_run(self._publish_next_post)
        self._safe_run(self._publish_next_reel)
        self._safe_run(self._publish_next_story)
        self._safe_run(self._publish_calendar_entries)
        if self._engagement:
            self._safe_run(self._engagement.engage_with_targets)
            self._safe_run(self._engagement.discover_and_engage)
        logger.info("Single run complete.")

    def start(self) -> None:
        """Register all jobs and enter the infinite scheduling loop."""
        self._register_content_jobs()
        self._register_calendar_job()
        self._register_engagement_jobs()

        logger.info(
            "Agent scheduler started (publishing via %s). Press Ctrl+C to stop.",
            "Graph API" if self._graph else "instagrapi",
        )
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
