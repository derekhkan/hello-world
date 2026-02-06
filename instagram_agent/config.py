"""Load and validate the YAML configuration file."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ScheduleSlot:
    enabled: bool = True
    times: List[str] = field(default_factory=lambda: ["09:00"])


@dataclass
class ContentConfig:
    media_dir: str = "./media"
    posts_schedule: ScheduleSlot = field(default_factory=ScheduleSlot)
    reels_schedule: ScheduleSlot = field(default_factory=ScheduleSlot)
    stories_schedule: ScheduleSlot = field(default_factory=ScheduleSlot)
    default_hashtags: List[str] = field(default_factory=list)
    default_location: Optional[int] = None


@dataclass
class EngagementConfig:
    enabled: bool = True
    target_accounts: List[str] = field(default_factory=list)
    discovery_hashtags: List[str] = field(default_factory=list)
    likes_per_account: int = 3
    commenting_enabled: bool = True
    comment_templates: List[str] = field(
        default_factory=lambda: ["Great post!"]
    )
    delay_min: int = 30
    delay_max: int = 90


@dataclass
class AppConfig:
    username: str = ""
    password: str = ""
    content: ContentConfig = field(default_factory=ContentConfig)
    engagement: EngagementConfig = field(default_factory=EngagementConfig)
    log_level: str = "INFO"
    log_file: str = "agent.log"


def load_config(path: str | Path = "config.yaml") -> AppConfig:
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
    defaults = content_raw.get("defaults", {})
    eng = raw.get("engagement", {})
    log_raw = raw.get("logging", {})

    content = ContentConfig(
        media_dir=content_raw.get("media_dir", "./media"),
        posts_schedule=ScheduleSlot(
            enabled=sched.get("posts", {}).get("enabled", True),
            times=sched.get("posts", {}).get("times", ["09:00"]),
        ),
        reels_schedule=ScheduleSlot(
            enabled=sched.get("reels", {}).get("enabled", True),
            times=sched.get("reels", {}).get("times", ["12:00"]),
        ),
        stories_schedule=ScheduleSlot(
            enabled=sched.get("stories", {}).get("enabled", True),
            times=sched.get("stories", {}).get("times", ["08:00"]),
        ),
        default_hashtags=defaults.get("hashtags", []),
        default_location=defaults.get("location"),
    )

    engagement = EngagementConfig(
        enabled=eng.get("enabled", True),
        target_accounts=eng.get("target_accounts", []),
        discovery_hashtags=eng.get("discovery_hashtags", []),
        likes_per_account=eng.get("likes_per_account", 3),
        commenting_enabled=eng.get("commenting", {}).get("enabled", True),
        comment_templates=eng.get("commenting", {}).get(
            "templates", ["Great post!"]
        ),
        delay_min=eng.get("delay", {}).get("min_seconds", 30),
        delay_max=eng.get("delay", {}).get("max_seconds", 90),
    )

    return AppConfig(
        username=account.get("username", ""),
        password=account.get("password", ""),
        content=content,
        engagement=engagement,
        log_level=log_raw.get("level", "INFO"),
        log_file=log_raw.get("file", "agent.log"),
    )
