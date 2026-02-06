"""Content calendar — translate a weekly theme into a concrete 7-day
YouTube publishing plan with varied titles and descriptions.

Content types: video, short, community
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

from youtube_agent.content_generator import (
    ContentGenerator,
    GenerationConfig,
)

logger = logging.getLogger(__name__)

CALENDAR_FILE = Path("yt_calendar.json")

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

CONTENT_TYPES = ("video", "short", "community")


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
# Title & description templates
# ---------------------------------------------------------------------------

VIDEO_ANGLES = [
    "Why {noun} Is the Key to Everything | Full Breakdown",
    "I Tried {gerund} for 30 Days — Here's What Happened",
    "The Truth About {noun} Nobody Talks About",
    "How to {verb} When You Don't Feel Like It",
    "{noun}: The One Thing Separating You From Success",
    "Stop Doing This If You Want {noun} in Your Life",
    "The Science Behind {noun} — Why It Actually Works",
    "My {adj} Morning Routine That Changed Everything",
    "{gerund} Is Harder Than You Think — Watch This First",
    "I Asked 100 People About {noun}. Their Answers Shocked Me.",
    "Why Most People Fail at {gerund} (And How to Fix It)",
    "The {adj} Mindset: How I Built Unshakeable Habits",
]

SHORT_ANGLES = [
    "60 seconds on {noun}. Watch this. 🔥",
    "POV: You decided to {verb} today.",
    "They told me {gerund} was pointless. I proved them wrong.",
    "Quick truth bomb about {noun}. #shorts",
    "The {adj} person in the room always wins.",
    "Day in my life: {gerund} edition. #shorts",
    "3 signs you need more {noun} in your life.",
    "If you're not {gerund}, you're falling behind.",
    "One simple rule: {verb}. Every. Single. Day.",
    "This is what {noun} looks like at 5 AM. #shorts",
]

COMMUNITY_ANGLES = [
    "Quick question for the community: what does {noun} mean to you? Drop your thoughts below 👇",
    "POLL: What's harder — starting to {verb} or maintaining it long-term?",
    "New video dropping soon on {noun}. What specific questions do you want me to answer?",
    "Real talk: {gerund} isn't glamorous, but it's how you win. Who's with me?",
    "Share your biggest {noun} win this week! Let's celebrate the small victories 🏆",
    "Hot take: {noun} is more important than talent. Agree or disagree?",
    "Behind the scenes of {gerund} — the stuff I don't put in videos. AMA 👇",
    "Reminder: being {adj} today means a better tomorrow. Keep going.",
]


# ---------------------------------------------------------------------------
# Weekly blueprint
# ---------------------------------------------------------------------------

WEEKLY_BLUEPRINT = [
    (0, "10:00", "video"),
    (0, "14:00", "community"),
    (1, "12:00", "short"),
    (1, "16:00", "community"),
    (2, "10:00", "video"),
    (2, "15:00", "short"),
    (3, "12:00", "short"),
    (3, "18:00", "community"),
    (4, "10:00", "video"),
    (4, "14:00", "short"),
    (5, "11:00", "short"),
    (5, "16:00", "community"),
    (6, "10:00", "video"),
    (6, "15:00", "short"),
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
        if ctype == "video":
            pool = VIDEO_ANGLES
        elif ctype == "short":
            pool = SHORT_ANGLES
        elif ctype == "community":
            pool = COMMUNITY_ANGLES
        else:
            pool = VIDEO_ANGLES

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
        if ctype == "video":
            return self._generator.generate_thumbnail(text=caption)
        elif ctype == "short":
            return self._generator.generate_short_thumbnail(text=caption)
        elif ctype == "community":
            return self._generator.generate_community_image(text=caption)
        else:
            raise ValueError(f"Unknown content type: {ctype}")

    @staticmethod
    def summarize(calendar: ContentCalendar) -> str:
        lines = [
            f"YouTube Content Calendar — \"{calendar.theme}\"",
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
                f"    {e.time}  [{e.content_type:9s}] {e.caption[:65]}  ({status})"
            )
        return "\n".join(lines)
