"""Configuration management for the job application agent."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from job_agent.models import SearchPreferences, UserProfile

load_dotenv()

DEFAULT_CONFIG_DIR = Path.home() / ".job-agent"
DEFAULT_DB_PATH = DEFAULT_CONFIG_DIR / "applications.db"
DEFAULT_DATA_DIR = DEFAULT_CONFIG_DIR / "data"


class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o"
    api_key: str = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    temperature: float = 0.7
    max_tokens: int = 2000


class BrowserConfig(BaseModel):
    headless: bool = True
    timeout: int = 30
    user_agent: str = ""
    proxy: str = ""


class NotificationConfig(BaseModel):
    enabled: bool = False
    smtp_host: str = Field(default_factory=lambda: os.getenv("SMTP_HOST", ""))
    smtp_port: int = Field(
        default_factory=lambda: int(os.getenv("SMTP_PORT", "587"))
    )
    smtp_email: str = Field(default_factory=lambda: os.getenv("SMTP_EMAIL", ""))
    smtp_password: str = Field(
        default_factory=lambda: os.getenv("SMTP_PASSWORD", "")
    )
    recipient_email: str = Field(
        default_factory=lambda: os.getenv("NOTIFICATION_EMAIL", "")
    )
    notify_on_apply: bool = True
    notify_on_error: bool = True
    daily_summary: bool = True


class AgentConfig(BaseModel):
    config_dir: Path = DEFAULT_CONFIG_DIR
    db_path: Path = DEFAULT_DB_PATH
    data_dir: Path = DEFAULT_DATA_DIR
    profile: UserProfile = Field(default_factory=UserProfile)
    search: SearchPreferences = Field(default_factory=SearchPreferences)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    notifications: NotificationConfig = Field(default_factory=NotificationConfig)
    rate_limit_delay: float = 2.0
    max_retries: int = 3
    dedup_window_days: int = 30

    class Config:
        arbitrary_types_allowed = True


def load_config(config_path: Path | None = None) -> AgentConfig:
    """Load configuration from YAML file, falling back to defaults."""
    if config_path is None:
        config_path = DEFAULT_CONFIG_DIR / "config.yaml"

    if config_path.exists():
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
        return AgentConfig(**raw)

    return AgentConfig()


def save_config(config: AgentConfig, config_path: Path | None = None) -> None:
    """Save current configuration to YAML file."""
    if config_path is None:
        config_path = config.config_dir / "config.yaml"

    config_path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(mode="json")
    # Convert Path objects to strings for YAML serialization
    for key in ("config_dir", "db_path", "data_dir"):
        if key in data:
            data[key] = str(data[key])

    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def init_config_dir(config: AgentConfig) -> None:
    """Create necessary directories for the agent."""
    config.config_dir.mkdir(parents=True, exist_ok=True)
    config.data_dir.mkdir(parents=True, exist_ok=True)
    (config.data_dir / "resumes").mkdir(exist_ok=True)
    (config.data_dir / "cover_letters").mkdir(exist_ok=True)
    (config.data_dir / "exports").mkdir(exist_ok=True)
