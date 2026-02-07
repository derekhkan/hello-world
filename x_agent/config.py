"""Configuration loader for the X agent."""

import os
import yaml


def load_config(path: str = "x_config.yaml") -> dict:
    """Load and validate configuration from YAML file.

    Environment variables override YAML values when set:
        X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET,
        X_BEARER_TOKEN, LLM_API_KEY
    """
    with open(path, "r") as f:
        config = yaml.safe_load(f)

    # Environment variable overrides for secrets
    env_overrides = {
        "X_API_KEY": ("twitter", "api_key"),
        "X_API_SECRET": ("twitter", "api_secret"),
        "X_ACCESS_TOKEN": ("twitter", "access_token"),
        "X_ACCESS_TOKEN_SECRET": ("twitter", "access_token_secret"),
        "X_BEARER_TOKEN": ("twitter", "bearer_token"),
        "LLM_API_KEY": ("llm", "api_key"),
    }

    for env_var, (section, key) in env_overrides.items():
        value = os.environ.get(env_var)
        if value:
            config.setdefault(section, {})[key] = value

    _validate(config)
    _apply_defaults(config)
    return config


def _validate(config: dict):
    """Validate required config fields are present."""
    required = [
        ("twitter", "api_key"),
        ("twitter", "api_secret"),
        ("twitter", "access_token"),
        ("twitter", "access_token_secret"),
        ("twitter", "bearer_token"),
        ("llm", "api_key"),
    ]
    missing = []
    for section, key in required:
        if not config.get(section, {}).get(key):
            missing.append(f"{section}.{key}")

    if missing:
        raise ValueError(
            f"Missing required config values: {', '.join(missing)}. "
            "Set them in x_config.yaml or via environment variables."
        )


def _apply_defaults(config: dict):
    """Apply default values for optional settings."""
    llm = config.setdefault("llm", {})
    llm.setdefault("provider", "anthropic")
    llm.setdefault("model", "claude-sonnet-4-5-20250929")

    schedule = config.setdefault("schedule", {})
    schedule.setdefault("posts_per_day", 2)
    schedule.setdefault("default_times", ["08:00", "17:00"])
    schedule.setdefault("timezone", "US/Eastern")

    ab = schedule.setdefault("ab_testing", {})
    ab.setdefault("enabled", True)
    ab.setdefault("morning_slots", ["07:00", "08:00", "09:00", "10:00"])
    ab.setdefault("evening_slots", ["16:00", "17:00", "18:00", "19:00"])
    ab.setdefault("epsilon", 0.3)
    ab.setdefault("min_samples", 5)

    config.setdefault("news_sources", [
        {"url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "name": "CoinDesk", "type": "rss"},
        {"url": "https://www.theblock.co/", "name": "The Block", "type": "html"},
        {"url": "https://cointelegraph.com/rss", "name": "CoinTelegraph", "type": "rss"},
    ])

    config.setdefault("data_dir", "data")
