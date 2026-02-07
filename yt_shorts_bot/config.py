"""Central configuration loaded from environment / .env / config.yaml."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "output"
ASSETS_DIR = ROOT_DIR / "yt_shorts_bot" / "assets"


class MidjourneySettings(BaseSettings):
    """Settings for Midjourney image generation."""

    model_config = SettingsConfigDict(env_prefix="MIDJOURNEY_")

    api_url: str = Field(
        default="https://api.midjourney.com",
        description="Midjourney API base URL (or compatible proxy)",
    )
    api_key: str = Field(default="", description="API key / token for Midjourney proxy")
    default_params: str = Field(
        default="--ar 9:16 --style raw --v 6",
        description="Default Midjourney parameters appended to every prompt",
    )
    timeout: int = Field(default=120, description="Max seconds to wait for image generation")


class VideoSettings(BaseSettings):
    """Settings for video assembly."""

    model_config = SettingsConfigDict(env_prefix="VIDEO_")

    width: int = 1080
    height: int = 1920
    fps: int = 30
    duration_per_image: float = Field(default=3.0, description="Seconds each image is shown")
    transition_duration: float = Field(default=0.5, description="Cross-fade seconds")
    max_duration: float = Field(default=59.0, description="YouTube Shorts must be ≤60 s")
    tts_voice: str = Field(default="en-US-ChristopherNeural", description="edge-tts voice name")


class YouTubeSettings(BaseSettings):
    """Settings for YouTube Data API uploads."""

    model_config = SettingsConfigDict(env_prefix="YOUTUBE_")

    client_secrets_file: str = Field(
        default="client_secrets.json",
        description="Path to OAuth2 client secrets JSON",
    )
    token_file: str = Field(default="token.json", description="Cached OAuth2 token")
    category_id: str = Field(default="22", description="YouTube video category (22 = People & Blogs)")
    privacy_status: str = Field(default="public", description="public | unlisted | private")
    default_tags: list[str] = Field(
        default_factory=lambda: ["shorts", "ai", "midjourney", "nanobanana"],
    )


class Settings(BaseSettings):
    """Top-level settings aggregating all sub-configs."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    midjourney: MidjourneySettings = Field(default_factory=MidjourneySettings)
    video: VideoSettings = Field(default_factory=VideoSettings)
    youtube: YouTubeSettings = Field(default_factory=YouTubeSettings)

    # Global
    output_dir: Path = Field(default=OUTPUT_DIR)
    log_level: str = Field(default="INFO")


def load_settings() -> Settings:
    """Load and return validated settings."""
    settings = Settings()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    return settings
