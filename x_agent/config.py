"""Load and validate the YAML configuration file for the X (Twitter) agent."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

from x_agent.content_generator import GenerationConfig

logger = logging.getLogger(__name__)


@dataclass
class ScheduleSlot:
    enabled: bool = True
    times: List[str] = field(default_factory=lambda: ["08:00"])


@dataclass
class ContentConfig:
    media_dir: str = "./media"
    tweets_schedule: ScheduleSlot = field(default_factory=ScheduleSlot)
    threads_schedule: ScheduleSlot = field(default_factory=ScheduleSlot)
    media_posts_schedule: ScheduleSlot = field(default_factory=ScheduleSlot)
    default_hashtags: List[str] = field(default_factory=list)


@dataclass
class EngagementConfig:
    enabled: bool = True
    target_accounts: List[str] = field(default_factory=list)
    discovery_keywords: List[str] = field(default_factory=list)
    likes_per_account: int = 3
    replying_enabled: bool = True
    reply_templates: List[str] = field(
        default_factory=lambda: ["Great post! Very insightful."]
    )
    retweet_enabled: bool = True
    delay_min: int = 30
    delay_max: int = 90


@dataclass
class AppConfig:
    api_key: str = ""
    api_secret: str = ""
    access_token: str = ""
    access_token_secret: str = ""
    bearer_token: str = ""
    content: ContentConfig = field(default_factory=ContentConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    engagement: EngagementConfig = field(default_factory=EngagementConfig)
    log_level: str = "INFO"
    log_file: str = "x_agent.log"


def load_config(path: str | Path = "x_config.yaml") -> AppConfig:
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
        tweets_schedule=ScheduleSlot(
            enabled=sched.get("tweets", {}).get("enabled", True),
            times=sched.get("tweets", {}).get("times", ["08:00", "12:00", "18:00"]),
        ),
        threads_schedule=ScheduleSlot(
            enabled=sched.get("threads", {}).get("enabled", True),
            times=sched.get("threads", {}).get("times", ["10:00"]),
        ),
        media_posts_schedule=ScheduleSlot(
            enabled=sched.get("media_posts", {}).get("enabled", True),
            times=sched.get("media_posts", {}).get("times", ["14:00"]),
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
        target_accounts=eng.get("target_accounts", []),
        discovery_keywords=eng.get("discovery_keywords", []),
        likes_per_account=eng.get("likes_per_account", 3),
        replying_enabled=eng.get("replying", {}).get("enabled", True),
        reply_templates=eng.get("replying", {}).get(
            "templates", ["Great post!"]
        ),
        retweet_enabled=eng.get("retweet", {}).get("enabled", True),
        delay_min=eng.get("delay", {}).get("min_seconds", 30),
        delay_max=eng.get("delay", {}).get("max_seconds", 90),
    )

    return AppConfig(
        api_key=account.get("api_key", "") or os.environ.get("X_API_KEY", ""),
        api_secret=account.get("api_secret", "") or os.environ.get("X_API_SECRET", ""),
        access_token=account.get("access_token", "") or os.environ.get("X_ACCESS_TOKEN", ""),
        access_token_secret=account.get("access_token_secret", "") or os.environ.get("X_ACCESS_TOKEN_SECRET", ""),
        bearer_token=account.get("bearer_token", "") or os.environ.get("X_BEARER_TOKEN", ""),
        content=content,
        generation=generation,
        engagement=engagement,
        log_level=log_raw.get("level", "INFO"),
        log_file=log_raw.get("file", "x_agent.log"),
    )
