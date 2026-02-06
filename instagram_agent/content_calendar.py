"""Content calendar — translate a weekly theme into a concrete 7-day
publishing plan, generate the media, and persist the calendar as JSON so
the scheduler knows exactly what to post and when.

Typical workflow
----------------
1. User sets a theme:  ``python main.py theme "Minimalist productivity"``
2. The ``ThemePlanner`` creates a 7-day ``ContentCalendar`` and generates
   all media up front.
3. The ``AgentScheduler`` reads the calendar and publishes each item at its
   scheduled time.

Calendar file: ``calendar.json`` in the project root (git-ignored).
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

from instagram_agent.content_generator import (
    ContentGenerator,
    GenerationConfig,
)

logger = logging.getLogger(__name__)

CALENDAR_FILE = Path("calendar.json")

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

CONTENT_TYPES = ("post", "reel", "story")


@dataclass
class CalendarEntry:
    """A single scheduled content item."""

    id: str
    day: str  # ISO date, e.g. "2025-06-15"
    time: str  # HH:MM
    content_type: str  # "post" | "reel" | "story"
    theme: str
    caption: str
    media_path: str = ""
    published: bool = False


@dataclass
class ContentCalendar:
    """A full 7-day (or N-day) content plan."""

    theme: str
    start_date: str
    entries: List[CalendarEntry] = field(default_factory=list)

    # -- Persistence -------------------------------------------------------

    def save(self, path: Path = CALENDAR_FILE) -> None:
        with open(path, "w") as fh:
            json.dump(asdict(self), fh, indent=2)
        logger.info("Calendar saved to %s (%d entries)", path, len(self.entries))

    @classmethod
    def load(cls, path: Path = CALENDAR_FILE) -> "ContentCalendar":
        with open(path) as fh:
            raw = json.load(fh)
        entries = [CalendarEntry(**e) for e in raw.get("entries", [])]
        return cls(
            theme=raw["theme"],
            start_date=raw["start_date"],
            entries=entries,
        )

    # -- Queries -----------------------------------------------------------

    def pending_for_today(self) -> List[CalendarEntry]:
        today = date.today().isoformat()
        return [
            e for e in self.entries if e.day == today and not e.published
        ]

    def mark_published(self, entry_id: str) -> None:
        for e in self.entries:
            if e.id == entry_id:
                e.published = True
                return


# ---------------------------------------------------------------------------
# Default weekly content blueprint
# ---------------------------------------------------------------------------

# Each day gets a mix of content types and a sub-theme derived from the main
# theme.  The ``caption_template`` uses Python format strings filled in by
# the planner.

WEEKLY_BLUEPRINT = [
    # (day_offset, time, content_type, caption_template)
    (0, "09:00", "post",  "Week kick-off: {theme} — let's go!"),
    (0, "12:00", "story", "Behind the scenes: getting ready for a week of {theme}."),
    (1, "09:00", "post",  "Day 2 of {theme}: diving deeper."),
    (1, "18:00", "story", "Quick tip about {theme}."),
    (2, "10:00", "reel",  "{theme} — the journey so far (mini recap)."),
    (2, "15:00", "story", "What inspires me about {theme}."),
    (3, "09:00", "post",  "Midweek motivation: {theme} edition."),
    (3, "20:00", "story", "{theme} in action."),
    (4, "09:00", "post",  "Deep dive: my take on {theme}."),
    (4, "13:00", "story", "Q&A time — ask me anything about {theme}!"),
    (5, "10:00", "reel",  "{theme} highlights of the week."),
    (5, "17:00", "story", "Weekend vibes: {theme}."),
    (6, "11:00", "post",  "Week wrap-up: what I learned about {theme}."),
    (6, "19:00", "story", "See you next week! Reflecting on {theme}."),
]


# ---------------------------------------------------------------------------
# Theme planner
# ---------------------------------------------------------------------------

class ThemePlanner:
    """Takes a theme string and produces a ready-to-publish
    ``ContentCalendar`` with all media pre-generated."""

    def __init__(self, gen_config: GenerationConfig) -> None:
        self._generator = ContentGenerator(gen_config)
        self._gen_config = gen_config

    def plan(
        self,
        theme: str,
        start: Optional[date] = None,
        blueprint: Optional[list] = None,
    ) -> ContentCalendar:
        """Build a full calendar from *theme* and generate media for every
        entry."""
        start = start or date.today()
        blueprint = blueprint or WEEKLY_BLUEPRINT

        calendar = ContentCalendar(
            theme=theme,
            start_date=start.isoformat(),
        )

        for day_offset, time_str, ctype, caption_tpl in blueprint:
            entry_date = start + timedelta(days=day_offset)
            caption = caption_tpl.format(theme=theme)
            entry_id = uuid.uuid4().hex[:12]

            # Generate media
            media_path = self._generate_media(ctype, caption)

            entry = CalendarEntry(
                id=entry_id,
                day=entry_date.isoformat(),
                time=time_str,
                content_type=ctype,
                theme=theme,
                caption=caption,
                media_path=str(media_path),
            )
            calendar.entries.append(entry)
            logger.info(
                "Planned %s for %s @ %s — %s",
                ctype,
                entry_date.isoformat(),
                time_str,
                caption[:50],
            )

        calendar.save()
        return calendar

    def _generate_media(self, ctype: str, caption: str) -> Path:
        if ctype == "post":
            return self._generator.generate_post(text=caption)
        elif ctype == "story":
            return self._generator.generate_story(text=caption)
        elif ctype == "reel":
            slides = [caption, f"More about: {caption}", "Stay tuned!"]
            return self._generator.generate_reel(texts=slides)
        else:
            raise ValueError(f"Unknown content type: {ctype}")

    # ------------------------------------------------------------------
    # Show a human-readable summary
    # ------------------------------------------------------------------

    @staticmethod
    def summarize(calendar: ContentCalendar) -> str:
        lines = [
            f"Content Calendar — \"{calendar.theme}\"",
            f"Starts: {calendar.start_date}",
            f"Total items: {len(calendar.entries)}",
            "",
        ]
        current_day = ""
        for e in calendar.entries:
            if e.day != current_day:
                current_day = e.day
                lines.append(f"  {current_day}")
            status = "done" if e.published else "pending"
            lines.append(
                f"    {e.time}  [{e.content_type:5s}] {e.caption[:60]}  ({status})"
            )
        return "\n".join(lines)
