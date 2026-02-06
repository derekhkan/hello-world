"""Content calendar — translate a weekly theme into a concrete 7-day
publishing plan with varied captions, generate the media, and persist the
calendar as JSON so the scheduler knows exactly what to post and when.

Typical workflow
----------------
1. User sets a theme:  ``python main.py theme "Staying Disciplined"``
2. The ``ThemePlanner`` creates a 7-day ``ContentCalendar`` with unique
   caption copy for each slot — each one explores a different angle of the
   theme rather than repeating it verbatim.
3. The ``AgentScheduler`` reads the calendar and publishes each item at its
   scheduled time.

Calendar file: ``calendar.json`` in the project root (git-ignored).
"""

from __future__ import annotations

import json
import logging
import random
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
# Caption variation system
# ---------------------------------------------------------------------------
# Instead of repeating the theme word-for-word, each slot gets a unique
# angle.  The blueprint contains a *prompt style* that gets combined with
# randomly-selected angle templates.  This produces copy like:
#
#   Theme: "Staying Disciplined"
#   -> "Discipline is showing up day in and day out."
#   -> "Why is staying disciplined important? Because small wins stack up."
#   -> "You don't need motivation. You need discipline."
#
# The system works by defining angle *patterns* that riff on the theme from
# different perspectives.

# -- Angle templates -------------------------------------------------------
# {theme} is the user's raw theme string.  Each template explores a
# different sub-topic or emotional angle.

POST_ANGLES = [
    # Why it matters
    "Why does {theme} matter? Because the days you don't feel like it are the days that count the most.",
    "{theme} isn't about perfection. It's about showing up — day in, day out.",
    "The secret nobody talks about: {theme} is a choice you make before you feel ready.",
    "You don't need motivation. You need {theme}. Motivation fades. Habits don't.",
    "{theme} is the bridge between where you are and where you want to be.",
    "Everybody wants the results. Nobody wants to talk about {theme}. That's why most people quit.",
    # How it shows up
    "{theme} looks like getting up when the alarm goes off. No snooze. No debate.",
    "What does {theme} look like? It looks boring. It looks repetitive. And that's exactly why it works.",
    "{theme} is the workout you do when nobody's watching.",
    "Small wins, stacked daily. That's what {theme} really means.",
    "{theme} isn't loud. It's the quiet decision to keep going.",
    "People ask how I stay consistent. The answer is simple: {theme}.",
    # Personal / dad angle
    "My kids will never remember my excuses. But they'll remember my {theme}.",
    "{theme} today means a stronger example tomorrow. Your kids are watching.",
    "Being a dad taught me more about {theme} than any book ever could.",
    "{theme} — because the people counting on me don't take days off.",
]

STORY_ANGLES = [
    "Quick reminder: {theme} beats talent every single time.",
    "Day {day_num} of the week. Still locked in. {theme}.",
    "No shortcuts. Just {theme}.",
    "Ask yourself: did you show {theme} today?",
    "The compound effect of {theme} is real. Trust the process.",
    "Behind the scenes: what {theme} actually looks like at 5 AM.",
    "{theme}. That's it. That's the story.",
    "Hot take: {theme} is more important than motivation. Fight me.",
    "How do you practice {theme}? Drop your answer.",
    "Real talk — {theme} isn't always glamorous. But it's always worth it.",
    "Nobody posts about the boring parts of {theme}. Here it is.",
    "Today's non-negotiable: {theme}.",
]

REEL_ANGLES = [
    "{theme} — what it looks like vs. what it feels like.",
    "7 days of {theme}. Here's what happened.",
    "The truth about {theme} that nobody tells you.",
    "{theme} in action. No edits. No filters.",
    "Watch this before you skip your workout. {theme}.",
    "How {theme} changed everything for me this week.",
]


def _pick_angle(angles: list[str], theme: str, day_num: int) -> str:
    """Pick a random angle template and fill it in."""
    template = random.choice(angles)
    return template.format(theme=theme, day_num=day_num)


# ---------------------------------------------------------------------------
# Weekly blueprint (schedule only — captions come from angles)
# ---------------------------------------------------------------------------

WEEKLY_BLUEPRINT = [
    # (day_offset, time, content_type)
    (0, "09:00", "post"),
    (0, "12:00", "story"),
    (1, "09:00", "post"),
    (1, "18:00", "story"),
    (2, "10:00", "reel"),
    (2, "15:00", "story"),
    (3, "09:00", "post"),
    (3, "20:00", "story"),
    (4, "09:00", "post"),
    (4, "13:00", "story"),
    (5, "10:00", "reel"),
    (5, "17:00", "story"),
    (6, "11:00", "post"),
    (6, "19:00", "story"),
]


# ---------------------------------------------------------------------------
# Theme planner
# ---------------------------------------------------------------------------

class ThemePlanner:
    """Takes a theme string and produces a ready-to-publish
    ``ContentCalendar`` with unique, varied captions and pre-generated media."""

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
        entry.  Each entry gets a unique caption angle — no two posts say the
        same thing."""
        start = start or date.today()
        blueprint = blueprint or WEEKLY_BLUEPRINT

        calendar = ContentCalendar(
            theme=theme,
            start_date=start.isoformat(),
        )

        used_captions: set[str] = set()

        for day_offset, time_str, ctype in blueprint:
            entry_date = start + timedelta(days=day_offset)
            day_num = day_offset + 1

            # Pick a unique caption
            caption = self._unique_caption(ctype, theme, day_num, used_captions)
            used_captions.add(caption)

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
                caption[:60],
            )

        calendar.save()
        return calendar

    @staticmethod
    def _unique_caption(
        ctype: str,
        theme: str,
        day_num: int,
        used: set[str],
    ) -> str:
        """Pick a caption that hasn't been used yet."""
        if ctype == "post":
            pool = POST_ANGLES
        elif ctype == "story":
            pool = STORY_ANGLES
        elif ctype == "reel":
            pool = REEL_ANGLES
        else:
            pool = POST_ANGLES

        # Shuffle and pick the first unused one
        candidates = list(pool)
        random.shuffle(candidates)
        for template in candidates:
            caption = template.format(theme=theme, day_num=day_num)
            if caption not in used:
                return caption

        # Fallback: all used (shouldn't happen with enough templates)
        return candidates[0].format(theme=theme, day_num=day_num)

    def _generate_media(self, ctype: str, caption: str) -> Path:
        if ctype == "post":
            return self._generator.generate_post(text=caption)
        elif ctype == "story":
            return self._generator.generate_story(text=caption)
        elif ctype == "reel":
            slides = [caption, "Stay locked in.", "Show up. Every day."]
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
                f"    {e.time}  [{e.content_type:5s}] {e.caption[:70]}  ({status})"
            )
        return "\n".join(lines)
