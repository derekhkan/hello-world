"""Approval queue for reviewing tweets before posting."""

import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ApprovalQueue:
    """Manages a queue of generated tweets awaiting review.

    Workflow:
        1. generate() creates tweets and adds them to the queue
        2. User reviews with list/approve/reject/regenerate commands
        3. Approved tweets get posted at scheduled times
    """

    def __init__(self, config: dict):
        self.data_dir = config.get("data_dir", "data")
        self._queue_path = os.path.join(self.data_dir, "approval_queue.json")
        self._feedback_path = os.path.join(self.data_dir, "feedback_log.json")

    def add(self, tweet_data: dict) -> int:
        """Add a generated tweet to the queue. Returns its queue index."""
        queue = self._load_queue()
        entry = {
            "tweet": tweet_data.get("tweet", ""),
            "pillar": tweet_data.get("pillar", ""),
            "format": tweet_data.get("format", ""),
            "news": tweet_data.get("news"),
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "feedback": None,
        }
        queue.append(entry)
        self._save_queue(queue)
        return len(queue) - 1

    def list_pending(self) -> list[tuple[int, dict]]:
        """Return all pending tweets with their indices."""
        queue = self._load_queue()
        return [(i, entry) for i, entry in enumerate(queue) if entry["status"] == "pending"]

    def list_approved(self) -> list[tuple[int, dict]]:
        """Return all approved tweets ready to post."""
        queue = self._load_queue()
        return [(i, entry) for i, entry in enumerate(queue) if entry["status"] == "approved"]

    def approve(self, index: int, edited_text: str | None = None) -> dict:
        """Approve a tweet. Optionally provide edited text."""
        queue = self._load_queue()
        if index >= len(queue):
            raise IndexError(f"No tweet at index {index}")

        queue[index]["status"] = "approved"
        queue[index]["approved_at"] = datetime.utcnow().isoformat()
        if edited_text:
            queue[index]["original_tweet"] = queue[index]["tweet"]
            queue[index]["tweet"] = edited_text
        self._save_queue(queue)
        return queue[index]

    def reject(self, index: int, feedback: str = "") -> dict:
        """Reject a tweet with optional feedback for improving future generations."""
        queue = self._load_queue()
        if index >= len(queue):
            raise IndexError(f"No tweet at index {index}")

        queue[index]["status"] = "rejected"
        queue[index]["feedback"] = feedback
        queue[index]["rejected_at"] = datetime.utcnow().isoformat()
        self._save_queue(queue)

        # Log feedback for learning
        if feedback:
            self._log_feedback(queue[index], feedback)

        return queue[index]

    def mark_posted(self, index: int, tweet_id: str):
        """Mark an approved tweet as posted."""
        queue = self._load_queue()
        if index >= len(queue):
            return
        queue[index]["status"] = "posted"
        queue[index]["tweet_id"] = tweet_id
        queue[index]["posted_at"] = datetime.utcnow().isoformat()
        self._save_queue(queue)

    def pop_next_approved(self) -> tuple[int, dict] | None:
        """Get the next approved tweet to post."""
        for i, entry in self.list_approved():
            return (i, entry)
        return None

    def get_feedback_history(self) -> list[dict]:
        """Get all past feedback for prompt tuning."""
        if not os.path.exists(self._feedback_path):
            return []
        try:
            with open(self._feedback_path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []

    def clear_posted(self):
        """Remove all posted tweets from the queue."""
        queue = self._load_queue()
        queue = [e for e in queue if e["status"] != "posted"]
        self._save_queue(queue)

    def _log_feedback(self, entry: dict, feedback: str):
        """Persist feedback for future prompt improvement."""
        history = self.get_feedback_history()
        history.append({
            "tweet": entry["tweet"],
            "pillar": entry.get("pillar"),
            "format": entry.get("format"),
            "feedback": feedback,
            "timestamp": datetime.utcnow().isoformat(),
        })
        os.makedirs(self.data_dir, exist_ok=True)
        with open(self._feedback_path, "w") as f:
            json.dump(history, f, indent=2)

    def _load_queue(self) -> list[dict]:
        if os.path.exists(self._queue_path):
            try:
                with open(self._queue_path, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass
        return []

    def _save_queue(self, queue: list[dict]):
        os.makedirs(self.data_dir, exist_ok=True)
        with open(self._queue_path, "w") as f:
            json.dump(queue, f, indent=2)
