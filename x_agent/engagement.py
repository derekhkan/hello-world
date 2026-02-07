"""Engagement tracking — fetches and analyzes tweet performance."""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class EngagementTracker:
    """Fetches engagement metrics and feeds them back to the A/B scheduler."""

    def __init__(self, client, scheduler, calendar):
        """
        Args:
            client: XClient instance.
            scheduler: ABScheduler instance.
            calendar: ContentCalendar instance.
        """
        self.client = client
        self.scheduler = scheduler
        self.calendar = calendar

    def update_recent(self, hours: int = 48) -> list[dict]:
        """Fetch metrics for recent tweets and update A/B test results.

        Returns:
            List of tweet metric dicts that were updated.
        """
        history = self.calendar.get_history(days=3)
        if not history:
            logger.info("No posting history to check engagement for")
            return []

        updated = []
        for entry in history:
            tweet_id = entry.get("tweet_id")
            if not tweet_id:
                continue

            try:
                metrics = self.client.get_tweet_metrics(str(tweet_id))
            except Exception as e:
                logger.error(f"Failed to fetch metrics for {tweet_id}: {e}")
                continue

            if not metrics:
                continue

            # Feed back to A/B scheduler
            time_slot = entry.get("time_slot")
            if time_slot:
                group = _classify_group(time_slot)
                self.scheduler.record_result(time_slot, group, metrics)

            updated.append({
                "tweet_id": tweet_id,
                "text": entry.get("text", "")[:80],
                "metrics": metrics,
            })

        logger.info(f"Updated engagement for {len(updated)} tweets")
        return updated

    def get_summary(self, days: int = 7) -> dict:
        """Get engagement summary for recent tweets."""
        history = self.calendar.get_history(days=days)
        if not history:
            return {"total_posts": 0}

        # Fetch fresh metrics
        all_metrics = []
        for entry in history:
            tweet_id = entry.get("tweet_id")
            if not tweet_id:
                continue
            try:
                metrics = self.client.get_tweet_metrics(str(tweet_id))
                if metrics:
                    metrics["tweet_id"] = tweet_id
                    metrics["pillar"] = entry.get("pillar")
                    all_metrics.append(metrics)
            except Exception:
                continue

        if not all_metrics:
            return {"total_posts": len(history), "tracked": 0}

        return {
            "total_posts": len(history),
            "tracked": len(all_metrics),
            "totals": {
                "impressions": sum(m.get("impression_count", 0) for m in all_metrics),
                "likes": sum(m.get("like_count", 0) for m in all_metrics),
                "retweets": sum(m.get("retweet_count", 0) for m in all_metrics),
                "replies": sum(m.get("reply_count", 0) for m in all_metrics),
                "bookmarks": sum(m.get("bookmark_count", 0) for m in all_metrics),
            },
            "averages": {
                "impressions": round(sum(m.get("impression_count", 0) for m in all_metrics) / len(all_metrics), 1),
                "likes": round(sum(m.get("like_count", 0) for m in all_metrics) / len(all_metrics), 1),
                "retweets": round(sum(m.get("retweet_count", 0) for m in all_metrics) / len(all_metrics), 1),
                "replies": round(sum(m.get("reply_count", 0) for m in all_metrics) / len(all_metrics), 1),
            },
            "by_pillar": _group_by_pillar(all_metrics),
        }


def _classify_group(time_slot: str) -> str:
    """Classify a time slot as morning or evening."""
    hour = int(time_slot.split(":")[0])
    return "morning" if hour < 12 else "evening"


def _group_by_pillar(metrics: list[dict]) -> dict:
    """Group metrics by content pillar."""
    by_pillar = {}
    for m in metrics:
        pillar = m.get("pillar", "unknown")
        if pillar not in by_pillar:
            by_pillar[pillar] = {"count": 0, "impressions": 0, "likes": 0}
        by_pillar[pillar]["count"] += 1
        by_pillar[pillar]["impressions"] += m.get("impression_count", 0)
        by_pillar[pillar]["likes"] += m.get("like_count", 0)

    # Compute averages
    for pillar, data in by_pillar.items():
        if data["count"] > 0:
            data["avg_impressions"] = round(data["impressions"] / data["count"], 1)
            data["avg_likes"] = round(data["likes"] / data["count"], 1)

    return by_pillar
