"""Load and validate the YAML configuration file for the LinkedIn agent."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

from linkedin_agent.content_generator import GenerationConfig

logger = logging.getLogger(__name__)


@dataclass
class ScheduleSlot:
    enabled: bool = True
    times: List[str] = field(default_factory=lambda: ["09:00"])


@dataclass
class ContentConfig:
    media_dir: str = "./media"
    posts_schedule: ScheduleSlot = field(default_factory=ScheduleSlot)
    articles_schedule: ScheduleSlot = field(default_factory=ScheduleSlot)
    carousels_schedule: ScheduleSlot = field(default_factory=ScheduleSlot)
    default_hashtags: List[str] = field(default_factory=list)


@dataclass
class EngagementConfig:
    enabled: bool = True
    target_authors: List[str] = field(default_factory=list)
    discovery_keywords: List[str] = field(default_factory=list)
    likes_per_author: int = 3
    commenting_enabled: bool = True
    comment_templates: List[str] = field(
        default_factory=lambda: ["Great insight! Thanks for sharing."]
    )
    delay_min: int = 60
    delay_max: int = 180


@dataclass
class AppConfig:
    access_token: str = ""
    person_urn: str = ""
    content: ContentConfig = field(default_factory=ContentConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    engagement: EngagementConfig = field(default_factory=EngagementConfig)
    log_level: str = "INFO"
    log_file: str = "linkedin_agent.log"


def load_config(path: str | Path = "linkedin_config.yaml") -> AppConfig:
    """Read *path* and return a validated ``AppConfig``."""
    config_path = Path(path)
    if not config_path.exists():
        logger.error("Configuration file not found: %s", config_path)
        sys.exit(1)

    with open(config_path, "r") as fh:
        raw = yaml.safe_load(fh)

    account = raw.get("account", {})
    content_raw = raw.get("content", {})
    sched = content_raw.get("schedule", {})
    gen_raw = raw.get("generation", {})
    ai_raw = gen_raw.get("ai", {})
    eng = raw.get("engagement", {})
    log_raw = raw.get("logging", {})

    content = ContentConfig(
        media_dir=content_raw.get("media_dir", "./media"),
        posts_schedule=ScheduleSlot(
            enabled=sched.get("posts", {}).get("enabled", True),
            times=sched.get("posts", {}).get("times", ["08:00", "12:00"]),
        ),
        articles_schedule=ScheduleSlot(
            enabled=sched.get("articles", {}).get("enabled", True),
            times=sched.get("articles", {}).get("times", ["10:00"]),
        ),
        carousels_schedule=ScheduleSlot(
            enabled=sched.get("carousels", {}).get("enabled", True),
            times=sched.get("carousels", {}).get("times", ["14:00"]),
        ),
        default_hashtags=content_raw.get("default_hashtags", []),
    )

    generation = GenerationConfig(
        enabled=gen_raw.get("enabled", False),
        quotes=gen_raw.get("quotes", []),
        ai_enabled=ai_raw.get("enabled", False),
        openai_api_key=ai_raw.get("openai_api_key", "") or os.environ.get("OPENAI_API_KEY", ""),
        gemini_api_key=ai_raw.get("gemini_api_key", "") or os.environ.get("GEMINI_API_KEY", ""),
        ai_prompts=ai_raw.get("prompts", []),
        media_dir=content_raw.get("media_dir", "./media"),
    )

    engagement = EngagementConfig(
        enabled=eng.get("enabled", True),
        target_authors=eng.get("target_authors", []),
        discovery_keywords=eng.get("discovery_keywords", []),
        likes_per_author=eng.get("likes_per_author", 3),
        commenting_enabled=eng.get("commenting", {}).get("enabled", True),
        comment_templates=eng.get("commenting", {}).get(
            "templates", ["Great insight! Thanks for sharing."]
        ),
        delay_min=eng.get("delay", {}).get("min_seconds", 60),
        delay_max=eng.get("delay", {}).get("max_seconds", 180),
    )

    return AppConfig(
        access_token=account.get("access_token", "") or os.environ.get("LINKEDIN_ACCESS_TOKEN", ""),
        person_urn=account.get("person_urn", ""),
        content=content,
        generation=generation,
        engagement=engagement,
        log_level=log_raw.get("level", "INFO"),
        log_file=log_raw.get("file", "linkedin_agent.log"),
    )
