"""A/B testing scheduler for post times.

Uses epsilon-greedy multi-armed bandit to explore different posting times
and converge on the slots that yield the highest impressions + engagements.
"""

import json
import os
import random
import logging
from datetime import datetime

import pytz

logger = logging.getLogger(__name__)


class ABScheduler:
    """Schedules posts with A/B testing of time slots.

    Maintains two slot groups (morning and evening) and tracks performance
    metrics for each slot. Uses epsilon-greedy strategy to balance
    exploration of new time slots vs exploitation of known good ones.
    """

    def __init__(self, config: dict):
        schedule = config.get("schedule", {})
        ab = schedule.get("ab_testing", {})

        self.timezone = pytz.timezone(schedule.get("timezone", "US/Eastern"))
        self.enabled = ab.get("enabled", True)
        self.epsilon = ab.get("epsilon", 0.3)
        self.min_samples = ab.get("min_samples", 5)

        self.morning_slots = ab.get("morning_slots", ["07:00", "08:00", "09:00", "10:00"])
        self.evening_slots = ab.get("evening_slots", ["16:00", "17:00", "18:00", "19:00"])

        # Fallback when A/B testing is disabled
        self.default_times = schedule.get("default_times", ["08:00", "17:00"])

        self.data_dir = config.get("data_dir", "data")
        self._results_path = os.path.join(self.data_dir, "ab_test_results.json")
        self._results = self._load_results()

    def pick_times(self) -> tuple[str, str]:
        """Pick morning and evening post times for today.

        Returns:
            Tuple of (morning_time, evening_time) as "HH:MM" strings.
        """
        if not self.enabled:
            return (self.default_times[0], self.default_times[1])

        morning = self._pick_slot(self.morning_slots, "morning")
        evening = self._pick_slot(self.evening_slots, "evening")
        return (morning, evening)

    def record_result(self, time_slot: str, group: str, metrics: dict):
        """Record engagement results for a time slot.

        Args:
            time_slot: The "HH:MM" time the post was made.
            group: "morning" or "evening".
            metrics: Dict with impressions, likes, retweets, replies, etc.
        """
        key = f"{group}_{time_slot}"
        if key not in self._results:
            self._results[key] = {
                "time_slot": time_slot,
                "group": group,
                "samples": [],
            }

        score = self._compute_score(metrics)
        self._results[key]["samples"].append({
            "score": score,
            "metrics": metrics,
            "recorded_at": datetime.utcnow().isoformat(),
        })
        self._save_results()

    def get_report(self) -> dict:
        """Generate an A/B test performance report.

        Returns:
            Dict with per-slot stats and current best slots.
        """
        report = {"morning": {}, "evening": {}, "recommendation": {}}

        for key, data in self._results.items():
            group = data["group"]
            slot = data["time_slot"]
            samples = data["samples"]
            scores = [s["score"] for s in samples]

            if not scores:
                continue

            stats = {
                "time_slot": slot,
                "n_samples": len(scores),
                "avg_score": round(sum(scores) / len(scores), 2),
                "best_score": round(max(scores), 2),
                "worst_score": round(min(scores), 2),
                "avg_metrics": self._avg_metrics(samples),
            }
            report[group][slot] = stats

        # Determine best slots
        for group in ["morning", "evening"]:
            slots = report[group]
            if slots:
                best = max(slots.values(), key=lambda s: s["avg_score"])
                report["recommendation"][group] = {
                    "best_time": best["time_slot"],
                    "avg_score": best["avg_score"],
                    "n_samples": best["n_samples"],
                    "confidence": "high" if best["n_samples"] >= self.min_samples * 2 else
                                  "medium" if best["n_samples"] >= self.min_samples else "low",
                }

        return report

    def _pick_slot(self, slots: list[str], group: str) -> str:
        """Epsilon-greedy slot selection."""
        # Explore: pick random slot
        if random.random() < self.epsilon:
            chosen = random.choice(slots)
            logger.info(f"A/B explore: {group} → {chosen}")
            return chosen

        # Exploit: pick best known slot (or random if insufficient data)
        best_slot = None
        best_avg = -1

        for slot in slots:
            key = f"{group}_{slot}"
            data = self._results.get(key, {})
            samples = data.get("samples", [])

            if len(samples) < self.min_samples:
                # Not enough data — treat as explorable
                continue

            scores = [s["score"] for s in samples]
            avg = sum(scores) / len(scores)
            if avg > best_avg:
                best_avg = avg
                best_slot = slot

        if best_slot is None:
            # Not enough data for any slot — explore
            chosen = random.choice(slots)
            logger.info(f"A/B explore (insufficient data): {group} → {chosen}")
            return chosen

        logger.info(f"A/B exploit: {group} → {best_slot} (avg score: {best_avg:.2f})")
        return best_slot

    def _compute_score(self, metrics: dict) -> float:
        """Compute a composite engagement score.

        Weights: impressions × 1, likes × 3, retweets × 5, replies × 4, bookmarks × 4
        Normalized by impressions to get engagement rate, then scaled.
        """
        impressions = metrics.get("impression_count", metrics.get("impressions", 0))
        likes = metrics.get("like_count", metrics.get("likes", 0))
        retweets = metrics.get("retweet_count", metrics.get("retweets", 0))
        replies = metrics.get("reply_count", metrics.get("replies", 0))
        bookmarks = metrics.get("bookmark_count", metrics.get("bookmarks", 0))

        raw = likes * 3 + retweets * 5 + replies * 4 + bookmarks * 4

        if impressions > 0:
            # Engagement rate × 1000 + log of impressions for volume bonus
            import math
            score = (raw / impressions) * 1000 + math.log1p(impressions)
        else:
            score = float(raw)

        return round(score, 4)

    def _avg_metrics(self, samples: list[dict]) -> dict:
        """Compute average metrics across samples."""
        if not samples:
            return {}
        keys = ["impression_count", "like_count", "retweet_count", "reply_count", "bookmark_count"]
        avgs = {}
        for k in keys:
            values = [s["metrics"].get(k, 0) for s in samples]
            avgs[k] = round(sum(values) / len(values), 1) if values else 0
        return avgs

    def _load_results(self) -> dict:
        if os.path.exists(self._results_path):
            try:
                with open(self._results_path, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass
        return {}

    def _save_results(self):
        os.makedirs(self.data_dir, exist_ok=True)
        with open(self._results_path, "w") as f:
            json.dump(self._results, f, indent=2)
