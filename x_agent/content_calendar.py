"""Content calendar — translate a weekly theme into a concrete 7-day
X (Twitter) publishing plan with varied tweets, threads, and media posts."""

from __future__ import annotations

import json
import logging
import random
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional

from x_agent.content_generator import (
    ContentGenerator,
    GenerationConfig,
)

logger = logging.getLogger(__name__)

CALENDAR_FILE = Path("x_calendar.json")

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

CONTENT_TYPES = ("tweet", "thread", "media_post")


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
# Theme forms
# ---------------------------------------------------------------------------

@dataclass
class ThemeForms:
    raw: str
    noun: str
    verb: str
    gerund: str
    adj: str


KNOWN_THEMES: dict[str, dict[str, str]] = {
    "staying disciplined": {"noun": "discipline", "verb": "stay disciplined", "gerund": "staying disciplined", "adj": "disciplined"},
    "stay consistent": {"noun": "consistency", "verb": "stay consistent", "gerund": "staying consistent", "adj": "consistent"},
    "push through": {"noun": "perseverance", "verb": "push through", "gerund": "pushing through", "adj": "relentless"},
    "no excuses": {"noun": "accountability", "verb": "stop making excuses", "gerund": "cutting out excuses", "adj": "accountable"},
    "showing up": {"noun": "commitment", "verb": "show up", "gerund": "showing up", "adj": "committed"},
    "grinding": {"noun": "the grind", "verb": "keep grinding", "gerund": "grinding", "adj": "relentless"},
    "hard work": {"noun": "hard work", "verb": "work hard", "gerund": "working hard", "adj": "hardworking"},
    "mental toughness": {"noun": "mental toughness", "verb": "stay mentally tough", "gerund": "building mental toughness", "adj": "mentally tough"},
    "focus": {"noun": "focus", "verb": "stay focused", "gerund": "staying focused", "adj": "focused"},
    "balance": {"noun": "balance", "verb": "find balance", "gerund": "finding balance", "adj": "balanced"},
    "recovery": {"noun": "recovery", "verb": "recover properly", "gerund": "recovering", "adj": "recovered"},
    "strength": {"noun": "strength", "verb": "build strength", "gerund": "building strength", "adj": "strong"},
}


def _detect_forms(theme: str) -> ThemeForms:
    key = theme.lower().strip()
    if key in KNOWN_THEMES:
        m = KNOWN_THEMES[key]
        return ThemeForms(raw=theme, **m)
    lower = theme.lower()
    return ThemeForms(raw=theme, noun=lower, verb=lower, gerund=lower, adj=lower)


# ---------------------------------------------------------------------------
# Caption templates — tweets are capped at 280 chars
# ---------------------------------------------------------------------------

TWEET_ANGLES = [
    "{noun} isn't sexy. It's boring. It's repetitive. And that's exactly why it works.",
    "Most people don't lack talent. They lack {noun}.",
    "You don't need a new strategy. You need to {verb}. Consistently.",
    "The gap between where you are and where you want to be? {noun}.",
    "Hot take: {noun} > motivation. Every time.",
    "{gerund} when nobody's watching is the real flex.",
    "Your future self will thank you for being {adj} today.",
    "Everyone wants results. Nobody wants to {verb}. That's the difference.",
    "{noun} is not a talent. It's a decision you make every morning.",
    "Being {adj} is a superpower most people underestimate.",
    "Day by day, {gerund} compounds into something extraordinary.",
    "The {adj} person in the room always wins long-term.",
    "Stop waiting for motivation. Start with {noun}.",
    "Nobody talks about {gerund} because it's not flashy. But it's everything.",
    "If you want uncommon results, practice {noun} at an uncommon level.",
    "The secret? There is no secret. Just {verb}. Every single day.",
]

THREAD_ANGLES = [
    "A thread on {noun} — 7 things I wish I knew sooner:\n\n1/ {gerund} is a skill, not a trait. Here's why that matters...",
    "Why {noun} beats talent every single time (a thread):\n\n1/ Most people overvalue talent and undervalue {noun}...",
    "I've been {gerund} for years. Here are the uncomfortable truths:\n\n1/ It's never as glamorous as it looks...",
    "The {adj} mindset — a framework that changed everything for me:\n\n1/ It starts with identity, not willpower...",
    "Unpopular opinions about {noun} — thread:\n\n1/ {gerund} shouldn't require motivation...",
    "How to actually {verb} (not the generic advice you've heard before):\n\n1/ Start stupidly small...",
    "The compound effect of {gerund} — real numbers, real results:\n\n1/ Day 1 feels pointless. Day 100 feels different...",
    "What {gerund} taught me about life, work, and everything in between:\n\n1/ Small wins matter more than big goals...",
]

MEDIA_POST_ANGLES = [
    "Visual reminder: {noun} is not optional. It's the foundation.",
    "Save this. Share this. {verb}.",
    "The daily mantra: be {adj}. Every. Single. Day.",
    "{gerund} looks different for everyone. What does it look like for you?",
    "This is your sign to {verb} today. No excuses.",
    "Proof that {gerund} works: look at anyone successful. That's their secret.",
]


# ---------------------------------------------------------------------------
# Weekly blueprint
# ---------------------------------------------------------------------------

WEEKLY_BLUEPRINT = [
    (0, "08:00", "tweet"),
    (0, "12:00", "thread"),
    (0, "18:00", "tweet"),
    (1, "08:00", "tweet"),
    (1, "14:00", "media_post"),
    (2, "09:00", "thread"),
    (2, "17:00", "tweet"),
    (3, "08:00", "tweet"),
    (3, "13:00", "media_post"),
    (3, "19:00", "tweet"),
    (4, "08:00", "thread"),
    (4, "16:00", "tweet"),
    (5, "10:00", "tweet"),
    (5, "15:00", "media_post"),
    (6, "11:00", "tweet"),
    (6, "17:00", "thread"),
]


# ---------------------------------------------------------------------------
# Theme planner
# ---------------------------------------------------------------------------

class ThemePlanner:
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
        if ctype == "tweet":
            pool = TWEET_ANGLES
        elif ctype == "thread":
            pool = THREAD_ANGLES
        elif ctype == "media_post":
            pool = MEDIA_POST_ANGLES
        else:
            pool = TWEET_ANGLES

        fill = {
            "noun": forms.noun,
            "verb": forms.verb,
            "gerund": forms.gerund,
            "adj": forms.adj,
            "day_num": day_num,
        }

        candidates = list(pool)
        random.shuffle(candidates)
        for template in candidates:
            caption = template.format(**fill)
            if caption not in used:
                return caption

        return candidates[0].format(**fill)

    def _generate_media(self, ctype: str, caption: str) -> Path:
        if ctype == "tweet":
            return self._generator.generate_tweet_image(text=caption)
        elif ctype == "thread":
            return self._generator.generate_thread_image(text=caption)
        elif ctype == "media_post":
            return self._generator.generate_media_post(text=caption)
        else:
            raise ValueError(f"Unknown content type: {ctype}")

    @staticmethod
    def summarize(calendar: ContentCalendar) -> str:
        lines = [
            f"X (Twitter) Content Calendar — \"{calendar.theme}\"",
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
                f"    {e.time}  [{e.content_type:10s}] {e.caption[:60]}  ({status})"
            )
        return "\n".join(lines)
