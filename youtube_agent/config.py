"""Load and validate the YAML configuration file for YouTube agent."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

from youtube_agent.content_generator import GenerationConfig

logger = logging.getLogger(__name__)


@dataclass
class ScheduleSlot:
    enabled: bool = True
    times: List[str] = field(default_factory=lambda: ["10:00"])


@dataclass
class ContentConfig:
    media_dir: str = "./media"
    videos_schedule: ScheduleSlot = field(default_factory=ScheduleSlot)
    shorts_schedule: ScheduleSlot = field(default_factory=ScheduleSlot)
    community_schedule: ScheduleSlot = field(default_factory=ScheduleSlot)
    default_tags: List[str] = field(default_factory=list)
    default_category_id: str = "22"
    default_privacy: str = "public"


@dataclass
class EngagementConfig:
    enabled: bool = True
    target_channels: List[str] = field(default_factory=list)
    discovery_keywords: List[str] = field(default_factory=list)
    likes_per_channel: int = 3
    commenting_enabled: bool = True
    comment_templates: List[str] = field(
        default_factory=lambda: ["Great video! Very insightful."]
    )
    delay_min: int = 30
    delay_max: int = 90


@dataclass
class AppConfig:
    client_secrets_file: str = "client_secrets.json"
    api_key: str = ""
    content: ContentConfig = field(default_factory=ContentConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    engagement: EngagementConfig = field(default_factory=EngagementConfig)
    log_level: str = "INFO"
    log_file: str = "youtube_agent.log"


def load_config(path: str | Path = "youtube_config.yaml") -> AppConfig:
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
        videos_schedule=ScheduleSlot(
            enabled=sched.get("videos", {}).get("enabled", True),
            times=sched.get("videos", {}).get("times", ["10:00"]),
        ),
        shorts_schedule=ScheduleSlot(
            enabled=sched.get("shorts", {}).get("enabled", True),
            times=sched.get("shorts", {}).get("times", ["14:00"]),
        ),
        community_schedule=ScheduleSlot(
            enabled=sched.get("community", {}).get("enabled", True),
            times=sched.get("community", {}).get("times", ["16:00"]),
        ),
        default_tags=content_raw.get("default_tags", []),
        default_category_id=content_raw.get("category_id", "22"),
        default_privacy=content_raw.get("privacy", "public"),
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
        target_channels=eng.get("target_channels", []),
        discovery_keywords=eng.get("discovery_keywords", []),
        likes_per_channel=eng.get("likes_per_channel", 3),
        commenting_enabled=eng.get("commenting", {}).get("enabled", True),
        comment_templates=eng.get("commenting", {}).get(
            "templates", ["Great video!"]
        ),
        delay_min=eng.get("delay", {}).get("min_seconds", 30),
        delay_max=eng.get("delay", {}).get("max_seconds", 90),
    )

    return AppConfig(
        client_secrets_file=account.get("client_secrets_file", "client_secrets.json"),
        api_key=account.get("api_key", "") or os.environ.get("YOUTUBE_API_KEY", ""),
        content=content,
        generation=generation,
        engagement=engagement,
        log_level=log_raw.get("level", "INFO"),
        log_file=log_raw.get("file", "youtube_agent.log"),
    )
