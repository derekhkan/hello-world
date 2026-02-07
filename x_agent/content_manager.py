"""Content manager — orchestrates the full scan → generate → post pipeline."""

import logging
import time
from datetime import datetime

import pytz
import schedule as sched_lib

from x_agent.client import XClient
from x_agent.news_scanner import NewsScanner
from x_agent.content_generator import ContentGenerator
from x_agent.content_calendar import ContentCalendar
from x_agent.scheduler import ABScheduler
from x_agent.engagement import EngagementTracker
from x_agent.approval_queue import ApprovalQueue

logger = logging.getLogger(__name__)


class ContentManager:
    """Orchestrates the X agent pipeline."""

    def __init__(
        self,
        config: dict,
        client: XClient,
        news_scanner: NewsScanner,
        generator: ContentGenerator,
        calendar: ContentCalendar,
        scheduler: ABScheduler,
    ):
        self.config = config
        self.client = client
        self.news_scanner = news_scanner
        self.generator = generator
        self.calendar = calendar
        self.scheduler = scheduler
        self.engagement = EngagementTracker(client, scheduler, calendar)
        self.queue = ApprovalQueue(config)
        self.tz = pytz.timezone(config.get("schedule", {}).get("timezone", "US/Eastern"))

    def run_once(self, dry_run: bool = False) -> dict:
        """Run the full pipeline once: scan → generate → post.

        Args:
            dry_run: If True, generate but don't post.

        Returns:
            Dict with generated tweet and post result.
        """
        # 1. Scan news (use cache if fresh)
        logger.info("Scanning news sources...")
        articles = self.news_scanner.load_cache() or self.news_scanner.scan_all()

        # 2. Get takeaways
        logger.info("Extracting takeaways...")
        takeaways = self.news_scanner.get_takeaways(articles, count=3)

        # 3. Get next content assignment
        assignment = self.calendar.next_assignment()
        logger.info(f"Assignment: pillar={assignment['pillar']}, format={assignment['format']}")

        # 4. Generate tweet
        logger.info("Generating tweet...")
        takeaway = takeaways[0] if takeaways else None
        tweet_text = self.generator.generate_tweet(
            pillar=assignment["pillar"],
            fmt=assignment["format"],
            news_takeaway=takeaway,
        )
        logger.info(f"Generated ({len(tweet_text)} chars): {tweet_text}")

        if dry_run:
            return {
                "tweet": tweet_text,
                "pillar": assignment["pillar"],
                "format": assignment["format"],
                "news": takeaway,
                "posted": False,
            }

        # 5. Post
        logger.info("Posting tweet...")
        result = self.client.post_tweet(tweet_text)

        # 6. Record in calendar
        now = datetime.now(self.tz)
        time_slot = now.strftime("%H:%M")
        self.calendar.record_post({
            "id": result["id"],
            "tweet": tweet_text,
            "pillar": assignment["pillar"],
            "format": assignment["format"],
            "posted_at": now.isoformat(),
            "time_slot": time_slot,
        })

        return {
            "tweet": tweet_text,
            "tweet_id": result["id"],
            "pillar": assignment["pillar"],
            "format": assignment["format"],
            "news": takeaway,
            "posted": True,
            "time_slot": time_slot,
        }

    def scan_news(self) -> dict:
        """Scan news and return takeaways without posting."""
        articles = self.news_scanner.scan_all()
        takeaways = self.news_scanner.get_takeaways(articles, count=5)
        return {
            "articles_found": len(articles),
            "takeaways": takeaways,
        }

    def generate_preview(self, count: int = 2) -> list[dict]:
        """Generate tweets for preview without posting."""
        articles = self.news_scanner.load_cache() or self.news_scanner.scan_all()
        takeaways = self.news_scanner.get_takeaways(articles, count=count)
        assignments = self.calendar.next_batch(count)
        return self.generator.generate_batch(assignments, takeaways)

    def generate_to_queue(self, count: int = 2) -> list[dict]:
        """Generate tweets and add them to the approval queue."""
        articles = self.news_scanner.load_cache() or self.news_scanner.scan_all()
        takeaways = self.news_scanner.get_takeaways(articles, count=count)
        assignments = self.calendar.next_batch(count)
        tweets = self.generator.generate_batch(assignments, takeaways)

        results = []
        for t in tweets:
            idx = self.queue.add(t)
            results.append({"index": idx, **t})
        return results

    def post_approved(self) -> dict | None:
        """Post the next approved tweet from the queue."""
        item = self.queue.pop_next_approved()
        if not item:
            return None

        idx, entry = item
        logger.info(f"Posting approved tweet #{idx}...")
        result = self.client.post_tweet(entry["tweet"])

        now = datetime.now(self.tz)
        time_slot = now.strftime("%H:%M")
        self.calendar.record_post({
            "id": result["id"],
            "tweet": entry["tweet"],
            "pillar": entry.get("pillar"),
            "format": entry.get("format"),
            "posted_at": now.isoformat(),
            "time_slot": time_slot,
        })
        self.queue.mark_posted(idx, result["id"])

        return {
            "tweet": entry["tweet"],
            "tweet_id": result["id"],
            "pillar": entry.get("pillar"),
            "time_slot": time_slot,
        }

    def check_engagement(self) -> list[dict]:
        """Update engagement metrics for recent posts."""
        return self.engagement.update_recent()

    def get_engagement_summary(self, days: int = 7) -> dict:
        """Get engagement summary."""
        return self.engagement.get_summary(days)

    def get_ab_report(self) -> dict:
        """Get A/B test report."""
        return self.scheduler.get_report()

    def run_daemon(self, dry_run: bool = False, approval_mode: bool = False):
        """Run as a daemon, posting at scheduled times.

        Args:
            dry_run: Generate but don't post.
            approval_mode: If True, only post from the approved queue.
                Generate tweets to the queue instead of posting directly.

        Picks today's times via A/B scheduler, schedules posts, and also
        periodically checks engagement on recent tweets.
        """
        morning, evening = self.scheduler.pick_times()
        logger.info(f"Today's schedule: morning={morning}, evening={evening}")
        if approval_mode:
            logger.info("Approval mode ON. Will generate to queue and post approved tweets only.")

        def _post_job():
            try:
                if approval_mode:
                    # Try to post from approved queue first
                    result = self.post_approved()
                    if result:
                        logger.info(f"[POSTED from queue] {result['tweet'][:80]}...")
                    else:
                        # No approved tweets. Generate to queue for review
                        generated = self.generate_to_queue(count=1)
                        logger.info(f"[QUEUED for review] {generated[0]['tweet'][:80]}...")
                        logger.info("Run 'python main_x.py review' to approve pending tweets.")
                else:
                    result = self.run_once(dry_run=dry_run)
                    status = "DRY RUN" if dry_run else "POSTED"
                    logger.info(f"[{status}] {result['tweet'][:80]}...")
            except Exception as e:
                logger.error(f"Post job failed: {e}", exc_info=True)

        def _engagement_job():
            try:
                self.check_engagement()
            except Exception as e:
                logger.error(f"Engagement check failed: {e}", exc_info=True)

        def _reschedule_job():
            """Pick new times at midnight for the next day."""
            nonlocal morning, evening
            morning, evening = self.scheduler.pick_times()
            logger.info(f"Rescheduled: morning={morning}, evening={evening}")
            sched_lib.clear("post")
            sched_lib.every().day.at(morning, self.tz.zone).do(_post_job).tag("post")
            sched_lib.every().day.at(evening, self.tz.zone).do(_post_job).tag("post")

        # Schedule posts
        sched_lib.every().day.at(morning, self.tz.zone).do(_post_job).tag("post")
        sched_lib.every().day.at(evening, self.tz.zone).do(_post_job).tag("post")

        # Check engagement every 6 hours
        sched_lib.every(6).hours.do(_engagement_job).tag("engagement")

        # Reschedule at midnight for next day's A/B picks
        sched_lib.every().day.at("00:01", self.tz.zone).do(_reschedule_job).tag("reschedule")

        logger.info("Daemon started. Press Ctrl+C to stop.")
        try:
            while True:
                sched_lib.run_pending()
                time.sleep(30)
        except KeyboardInterrupt:
            logger.info("Daemon stopped.")
