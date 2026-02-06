"""Content calendar — translate a weekly theme into a concrete 7-day
LinkedIn publishing plan with varied, professional captions.

Content types: post, article, carousel
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

from linkedin_agent.content_generator import (
    ContentGenerator,
    GenerationConfig,
)

logger = logging.getLogger(__name__)

CALENDAR_FILE = Path("li_calendar.json")

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

CONTENT_TYPES = ("post", "article", "carousel")


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
    "leadership": {"noun": "leadership", "verb": "lead by example", "gerund": "leading", "adj": "effective"},
    "growth mindset": {"noun": "growth mindset", "verb": "embrace growth", "gerund": "growing", "adj": "growth-oriented"},
    "networking": {"noun": "networking", "verb": "build connections", "gerund": "networking", "adj": "connected"},
    "innovation": {"noun": "innovation", "verb": "innovate relentlessly", "gerund": "innovating", "adj": "innovative"},
    "resilience": {"noun": "resilience", "verb": "stay resilient", "gerund": "building resilience", "adj": "resilient"},
    "focus": {"noun": "focus", "verb": "stay focused", "gerund": "staying focused", "adj": "focused"},
    "mentorship": {"noun": "mentorship", "verb": "mentor others", "gerund": "mentoring", "adj": "mentored"},
    "personal brand": {"noun": "personal branding", "verb": "build your brand", "gerund": "building your brand", "adj": "branded"},
    "work-life balance": {"noun": "work-life balance", "verb": "find balance", "gerund": "finding balance", "adj": "balanced"},
    "continuous learning": {"noun": "continuous learning", "verb": "keep learning", "gerund": "learning continuously", "adj": "knowledgeable"},
}


def _detect_forms(theme: str) -> ThemeForms:
    key = theme.lower().strip()
    if key in KNOWN_THEMES:
        m = KNOWN_THEMES[key]
        return ThemeForms(raw=theme, **m)
    lower = theme.lower()
    return ThemeForms(raw=theme, noun=lower, verb=lower, gerund=lower, adj=lower)


# ---------------------------------------------------------------------------
# Caption templates — LinkedIn's professional tone
# ---------------------------------------------------------------------------

POST_ANGLES = [
    "I've been thinking about {noun} a lot lately.\n\nHere's what most professionals get wrong:\n\nThey wait for the perfect moment to {verb}. But the truth is, the perfect moment is right now.\n\nThe most {adj} people I know share one trait — they started before they were ready.",
    "Unpopular opinion: {noun} matters more than talent in your career.\n\nI've seen it play out hundreds of times. The {adj} professional always outlasts the naturally gifted one.\n\nAgreed? Disagree? I'd love to hear your perspective.",
    "3 things I learned about {noun} this year:\n\n1. It's a practice, not a destination\n2. Small wins compound over time\n3. The people who master {gerund} are the ones who succeed long-term\n\nWhich resonates with you most?",
    "Want to accelerate your career?\n\nStart {gerund}.\n\nNot tomorrow. Not next Monday. Today.\n\nThe gap between successful professionals and everyone else isn't talent — it's {noun}.",
    "The best career advice I ever received:\n\n\"{verb}. Even when it's uncomfortable. Especially when it's uncomfortable.\"\n\nThis simple principle has shaped every decision I've made since.",
    "People ask me what makes a great leader.\n\nMy answer always surprises them: {noun}.\n\nNot charisma. Not vision. Not strategy.\n\n{noun} is the foundation everything else is built on.",
    "I used to think {gerund} was optional.\n\nThen I watched the most successful people in my industry. They all share one thing in common:\n\nRelentless {noun}.\n\nHere's how you can develop it too...",
    "Hot take: Your LinkedIn network doesn't need more connections.\n\nIt needs more {adj} professionals who actually {verb}.\n\nQuality over quantity. Always.",
]

ARTICLE_ANGLES = [
    "The {adj} Professional's Guide to Career Growth — Why {noun} is the Missing Piece",
    "What 10 Years in Business Taught Me About {noun}",
    "The Hidden Cost of Ignoring {noun} in Your Career",
    "How {gerund} Transformed My Approach to Leadership",
    "Why Every Professional Should Learn to {verb}",
    "The Compound Effect of {gerund}: A Data-Driven Perspective",
]

CAROUSEL_ANGLES = [
    "Slide 1: The Ultimate Guide to {noun}\nSlide 2: Why it matters in 2025\nSlide 3: 5 steps to {verb}\nSlide 4: Common mistakes to avoid\nSlide 5: Start today",
    "Slide 1: {noun} — Myths vs. Reality\nSlide 2: Myth #1: It's only for senior leaders\nSlide 3: Myth #2: It can't be learned\nSlide 4: The truth: anyone can be {adj}\nSlide 5: Your action plan",
    "Slide 1: What {gerund} Looks Like in Practice\nSlide 2: Morning routine\nSlide 3: Workday habits\nSlide 4: Weekly reflection\nSlide 5: Long-term impact",
    "Slide 1: From Good to Great: The {noun} Framework\nSlide 2: Assess where you are\nSlide 3: Define your north star\nSlide 4: Build daily {adj} habits\nSlide 5: Measure and iterate",
]


# ---------------------------------------------------------------------------
# Weekly blueprint
# ---------------------------------------------------------------------------

WEEKLY_BLUEPRINT = [
    (0, "08:00", "post"),
    (0, "14:00", "carousel"),
    (1, "09:00", "post"),
    (2, "08:00", "article"),
    (2, "15:00", "post"),
    (3, "09:00", "post"),
    (3, "16:00", "carousel"),
    (4, "08:00", "post"),
    (5, "10:00", "post"),
    (5, "14:00", "carousel"),
    (6, "09:00", "post"),
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
        if ctype == "post":
            pool = POST_ANGLES
        elif ctype == "article":
            pool = ARTICLE_ANGLES
        elif ctype == "carousel":
            pool = CAROUSEL_ANGLES
        else:
            pool = POST_ANGLES

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
        if ctype == "post":
            return self._generator.generate_post_image(text=caption)
        elif ctype == "article":
            return self._generator.generate_article_cover(text=caption)
        elif ctype == "carousel":
            return self._generator.generate_carousel_slide(text=caption)
        else:
            raise ValueError(f"Unknown content type: {ctype}")

    @staticmethod
    def summarize(calendar: ContentCalendar) -> str:
        lines = [
            f"LinkedIn Content Calendar — \"{calendar.theme}\"",
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
                f"    {e.time}  [{e.content_type:8s}] {e.caption[:60]}  ({status})"
            )
        return "\n".join(lines)
