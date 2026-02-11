"""Content calendar — translate a weekly theme into a concrete 7-day
publishing plan with varied, grammatically natural captions.

The caption system uses multiple grammatical forms of the theme so copy
reads naturally in every context:

    Theme input:  "Staying Disciplined"
    noun form:    "discipline"        — "You need discipline."
    verb form:    "stay disciplined"  — "You need to stay disciplined."
    adj form:     "disciplined"       — "The most disciplined people win."
    gerund form:  "staying disciplined" — "Staying disciplined is a choice."

Users provide these forms via the CLI or they default to the raw theme.
"""

from __future__ import annotations

import json
import logging
import random
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

from instagram_agent.content_generator import (
    ContentGenerator,
    GenerationConfig,
)
from instagram_agent.quotes import DAD_STRENGTH_QUOTES

logger = logging.getLogger(__name__)

CALENDAR_FILE = Path("calendar.json")

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

CONTENT_TYPES = ("post", "reel", "story")


@dataclass
class CalendarEntry:
    id: str
    day: str
    time: str
    content_type: str
    theme: str
    caption: str
    media_path: str = ""
    published: bool = False


@dataclass
class ContentCalendar:
    theme: str
    start_date: str
    entries: List[CalendarEntry] = field(default_factory=list)

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

    def pending_for_today(self) -> List[CalendarEntry]:
        today = date.today().isoformat()
        return [e for e in self.entries if e.day == today and not e.published]

    def mark_published(self, entry_id: str) -> None:
        for e in self.entries:
            if e.id == entry_id:
                e.published = True
                return


# ---------------------------------------------------------------------------
# Theme forms — different grammatical versions of the theme
# ---------------------------------------------------------------------------
# Templates use these placeholders:
#   {noun}    — the core concept as a noun         ("discipline")
#   {verb}    — action/imperative form              ("stay disciplined")
#   {gerund}  — -ing form                           ("staying disciplined")
#   {adj}     — adjective form                      ("disciplined")
#   {day_num} — day of the week (1-7)
#
# Common themes and their forms:
#
#   "Staying Disciplined"  → noun=discipline,  verb=stay disciplined,
#                             gerund=staying disciplined, adj=disciplined
#   "Stay Consistent"      → noun=consistency, verb=stay consistent,
#                             gerund=staying consistent,  adj=consistent
#   "Push Through"         → noun=perseverance, verb=push through,
#                             gerund=pushing through,     adj=relentless
#   "No Excuses"           → noun=accountability, verb=stop making excuses,
#                             gerund=cutting out excuses, adj=accountable

@dataclass
class ThemeForms:
    """All grammatical forms of a theme for natural caption generation."""
    raw: str       # original theme string
    noun: str      # "discipline", "consistency"
    verb: str      # "stay disciplined", "be consistent"
    gerund: str    # "staying disciplined", "being consistent"
    adj: str       # "disciplined", "consistent"


# Well-known theme mappings for automatic form detection
KNOWN_THEMES: dict[str, dict[str, str]] = {
    "staying disciplined": {"noun": "discipline", "verb": "stay disciplined", "gerund": "staying disciplined", "adj": "disciplined"},
    "stay disciplined": {"noun": "discipline", "verb": "stay disciplined", "gerund": "staying disciplined", "adj": "disciplined"},
    "discipline": {"noun": "discipline", "verb": "stay disciplined", "gerund": "staying disciplined", "adj": "disciplined"},
    "staying consistent": {"noun": "consistency", "verb": "stay consistent", "gerund": "staying consistent", "adj": "consistent"},
    "stay consistent": {"noun": "consistency", "verb": "stay consistent", "gerund": "staying consistent", "adj": "consistent"},
    "consistency": {"noun": "consistency", "verb": "stay consistent", "gerund": "staying consistent", "adj": "consistent"},
    "push through": {"noun": "perseverance", "verb": "push through", "gerund": "pushing through", "adj": "relentless"},
    "pushing through": {"noun": "perseverance", "verb": "push through", "gerund": "pushing through", "adj": "relentless"},
    "no excuses": {"noun": "accountability", "verb": "stop making excuses", "gerund": "cutting out excuses", "adj": "accountable"},
    "showing up": {"noun": "commitment", "verb": "show up", "gerund": "showing up", "adj": "committed"},
    "show up": {"noun": "commitment", "verb": "show up", "gerund": "showing up", "adj": "committed"},
    "grinding": {"noun": "the grind", "verb": "keep grinding", "gerund": "grinding", "adj": "relentless"},
    "grind": {"noun": "the grind", "verb": "keep grinding", "gerund": "grinding", "adj": "relentless"},
    "hard work": {"noun": "hard work", "verb": "work hard", "gerund": "working hard", "adj": "hardworking"},
    "working hard": {"noun": "hard work", "verb": "work hard", "gerund": "working hard", "adj": "hardworking"},
    "mental toughness": {"noun": "mental toughness", "verb": "stay mentally tough", "gerund": "building mental toughness", "adj": "mentally tough"},
    "patience": {"noun": "patience", "verb": "be patient", "gerund": "being patient", "adj": "patient"},
    "being patient": {"noun": "patience", "verb": "be patient", "gerund": "being patient", "adj": "patient"},
    "focus": {"noun": "focus", "verb": "stay focused", "gerund": "staying focused", "adj": "focused"},
    "staying focused": {"noun": "focus", "verb": "stay focused", "gerund": "staying focused", "adj": "focused"},
    "balance": {"noun": "balance", "verb": "find balance", "gerund": "finding balance", "adj": "balanced"},
    "recovery": {"noun": "recovery", "verb": "recover properly", "gerund": "recovering", "adj": "recovered"},
    "strength": {"noun": "strength", "verb": "build strength", "gerund": "building strength", "adj": "strong"},
    "building strength": {"noun": "strength", "verb": "build strength", "gerund": "building strength", "adj": "strong"},
}


def _detect_forms(theme: str) -> ThemeForms:
    """Try to detect grammatical forms from known themes, otherwise
    use the raw theme everywhere (lowercase)."""
    key = theme.lower().strip()
    if key in KNOWN_THEMES:
        m = KNOWN_THEMES[key]
        return ThemeForms(raw=theme, **m)

    # Fallback: use the raw theme lowercased for all forms
    lower = theme.lower()
    return ThemeForms(raw=theme, noun=lower, verb=lower, gerund=lower, adj=lower)


# ---------------------------------------------------------------------------
# Caption templates — use {noun}, {verb}, {gerund}, {adj} for natural copy
# ---------------------------------------------------------------------------

POST_ANGLES = [
    # Why it matters
    "Why does {noun} matter? Because the days you don't feel like it are the days that count the most.",
    "{noun} isn't about perfection. It's about showing up — day in, day out.",
    "The secret nobody talks about: {noun} is a choice you make before you feel ready.",
    "You don't need motivation. You need {noun}. Motivation fades. Habits don't.",
    "{noun} is the bridge between where you are and where you want to be.",
    "Everybody wants the results. Nobody wants to talk about {noun}. That's why most people quit.",
    # How it shows up
    "What does it look like to {verb}? It looks boring. It looks repetitive. And that's exactly why it works.",
    "Being {adj} means getting up when the alarm goes off. No snooze. No debate.",
    "{gerund} is the workout you do when nobody's watching.",
    "Small wins, stacked daily. That's what it really means to {verb}.",
    "{gerund} isn't loud. It's the quiet decision to keep going.",
    "People ask how I stay consistent. The answer is simple: {noun}.",
    # Personal / dad angle
    "My kids will never remember my excuses. But they'll remember that I was {adj}.",
    "Being {adj} today means a stronger example tomorrow. Your kids are watching.",
    "Being a dad taught me more about {noun} than any book ever could.",
    "I {verb} because the people counting on me don't take days off.",
]

STORY_ANGLES = [
    "Quick reminder: {noun} beats talent every single time.",
    "Day {day_num} of the week. Still locked in. Still {adj}.",
    "No shortcuts. Just {noun}.",
    "Ask yourself: did you {verb} today?",
    "The compound effect of {gerund} is real. Trust the process.",
    "Behind the scenes: what it looks like to {verb} at 5 AM.",
    "{noun}. That's it. That's the story.",
    "Hot take: {noun} is more important than motivation. Fight me.",
    "How do you practice {gerund}? Drop your answer.",
    "Real talk — {gerund} isn't always glamorous. But it's always worth it.",
    "Nobody posts about the boring parts of {gerund}. Here it is.",
    "Today's non-negotiable: {verb}.",
]

REEL_ANGLES = [
    "{gerund} — what it looks like vs. what it feels like.",
    "7 days of {gerund}. Here's what happened.",
    "The truth about {noun} that nobody tells you.",
    "{noun} in action. No edits. No filters.",
    "Watch this before you skip your workout. {verb}.",
    "How {gerund} changed everything for me this week.",
]


# ---------------------------------------------------------------------------
# Weekly blueprint
# ---------------------------------------------------------------------------

WEEKLY_BLUEPRINT = [
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
    ``ContentCalendar`` with grammatically correct, varied captions."""

    def __init__(self, gen_config: GenerationConfig) -> None:
        self._generator = ContentGenerator(gen_config)
        self._gen_config = gen_config

    def plan(
        self,
        theme: str,
        start: Optional[date] = None,
        blueprint: Optional[list] = None,
        forms: Optional[ThemeForms] = None,
    ) -> ContentCalendar:
        start = start or date.today()
        blueprint = blueprint or WEEKLY_BLUEPRINT
        forms = forms or _detect_forms(theme)

        calendar = ContentCalendar(
            theme=theme,
            start_date=start.isoformat(),
        )

        used_captions: set[str] = set()

        for day_offset, time_str, ctype in blueprint:
            entry_date = start + timedelta(days=day_offset)
            day_num = day_offset + 1

            caption = self._unique_caption(ctype, forms, day_num, used_captions)
            used_captions.add(caption)

            entry_id = uuid.uuid4().hex[:12]
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
                ctype, entry_date.isoformat(), time_str, caption[:60],
            )

        calendar.save()
        return calendar

    @staticmethod
    def _unique_caption(
        ctype: str,
        forms: ThemeForms,
        day_num: int,
        used: set[str],
    ) -> str:
        if ctype == "post":
            pool = POST_ANGLES
        elif ctype == "story":
            pool = STORY_ANGLES
        elif ctype == "reel":
            pool = REEL_ANGLES
        else:
            pool = POST_ANGLES

        fill = {
            "noun": forms.noun,
            "verb": forms.verb,
            "gerund": forms.gerund,
            "adj": forms.adj,
            "day_num": day_num,
        }

        # 50/50 mix: half theme-based templates, half standalone quotes
        use_quote = random.random() < 0.5

        if use_quote:
            # Pick a standalone quote from the 500-quote bank
            quotes = list(DAD_STRENGTH_QUOTES)
            random.shuffle(quotes)
            for q in quotes:
                if q not in used:
                    return q

        # Theme-based template
        candidates = list(pool)
        random.shuffle(candidates)
        for template in candidates:
            caption = template.format(**fill)
            if caption not in used:
                return caption

        # Fallback to any unused quote
        for q in DAD_STRENGTH_QUOTES:
            if q not in used:
                return q

        return candidates[0].format(**fill)

    def _generate_media(self, ctype: str, caption: str) -> Path:
        if ctype == "post":
            return self._generator.generate_post(text=caption)
        elif ctype == "story":
            return self._generator.generate_story(text=caption)
        elif ctype == "reel":
            # Pick 2 random quotes for the extra slides
            extras = random.sample(DAD_STRENGTH_QUOTES, min(2, len(DAD_STRENGTH_QUOTES)))
            slides = [caption] + extras
            return self._generator.generate_reel(texts=slides)
        else:
            raise ValueError(f"Unknown content type: {ctype}")

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
