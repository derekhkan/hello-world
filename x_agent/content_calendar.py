"""Content calendar — manages pillar/format rotation and posting history."""

import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

PILLAR_ORDER = [
    "operator_stories",
    "web2_web3_translation",
    "user_empathy_metrics",
    "philosophy_for_builders",
]

FORMAT_ORDER = [
    "story_lesson_principle",
    "calm_contrarian",
    "web2_translation",
    "one_metric_truth",
]


class ContentCalendar:
    """Tracks pillar/format rotation and posting history.

    Cycles through all 4 pillars, and independently cycles through all 4
    formats. This gives 16 unique combinations before repeating.
    """

    def __init__(self, config: dict):
        self.data_dir = config.get("data_dir", "data")
        self._state_path = os.path.join(self.data_dir, "calendar_state.json")
        self._history_path = os.path.join(self.data_dir, "posted_tweets.json")
        self._state = self._load_state()

    def next_assignment(self) -> dict:
        """Return the next pillar + format assignment and advance rotation."""
        pillar_idx = self._state["pillar_index"] % len(PILLAR_ORDER)
        format_idx = self._state["format_index"] % len(FORMAT_ORDER)

        assignment = {
            "pillar": PILLAR_ORDER[pillar_idx],
            "format": FORMAT_ORDER[format_idx],
        }

        # Advance: pillar every post, format every full pillar cycle
        self._state["pillar_index"] += 1
        if self._state["pillar_index"] % len(PILLAR_ORDER) == 0:
            self._state["format_index"] += 1

        self._save_state()
        return assignment

    def next_batch(self, count: int) -> list[dict]:
        """Return the next N assignments."""
        return [self.next_assignment() for _ in range(count)]

    def record_post(self, tweet_data: dict):
        """Record a posted tweet in history."""
        history = self._load_history()
        entry = {
            "tweet_id": tweet_data.get("id"),
            "text": tweet_data.get("tweet", tweet_data.get("text", "")),
            "pillar": tweet_data.get("pillar"),
            "format": tweet_data.get("format"),
            "posted_at": tweet_data.get("posted_at", datetime.utcnow().isoformat()),
            "time_slot": tweet_data.get("time_slot"),
        }
        history.append(entry)
        self._save_history(history)

    def get_history(self, days: int = 7) -> list[dict]:
        """Get posting history for the last N days."""
        history = self._load_history()
        if not history:
            return []

        cutoff = datetime.utcnow().replace(
            hour=0, minute=0, second=0
        ).isoformat()
        # Simple filter: return last N * posts_per_day entries as approximation
        return history[-(days * 2):]

    def get_pillar_distribution(self, days: int = 7) -> dict[str, int]:
        """Count how many times each pillar was used recently."""
        history = self.get_history(days)
        dist = {p: 0 for p in PILLAR_ORDER}
        for entry in history:
            pillar = entry.get("pillar")
            if pillar in dist:
                dist[pillar] += 1
        return dist

    def _load_state(self) -> dict:
        if os.path.exists(self._state_path):
            try:
                with open(self._state_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, KeyError):
                pass
        return {"pillar_index": 0, "format_index": 0}

    def _save_state(self):
        os.makedirs(self.data_dir, exist_ok=True)
        with open(self._state_path, "w") as f:
            json.dump(self._state, f, indent=2)

    def _load_history(self) -> list[dict]:
        if os.path.exists(self._history_path):
            try:
                with open(self._history_path, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass
        return []

    def _save_history(self, history: list[dict]):
        os.makedirs(self.data_dir, exist_ok=True)
        with open(self._history_path, "w") as f:
            json.dump(history, f, indent=2)
