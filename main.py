#!/usr/bin/env python3
"""Entry point for the Instagram Automation Agent.

Usage
-----
Set a weekly theme and generate a 7-day content calendar::

    python main.py theme "Minimalist productivity"

View the current calendar::

    python main.py calendar

Run on a schedule (daemon mode)::

    python main.py run --config config.yaml

Execute every job once and exit::

    python main.py run --config config.yaml --once

Generate a batch of media without posting::

    python main.py generate --posts 3 --stories 2 --reels 1
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from instagram_agent.config import load_config

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def _setup_logging(level: str, log_file: str) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file),
    ]
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_theme(args: argparse.Namespace) -> None:
    """Set a weekly theme and generate a full content calendar."""
    config = load_config(args.config)
    _setup_logging(config.log_level, config.log_file)

    from instagram_agent.content_calendar import ThemePlanner
    planner = ThemePlanner(config.generation)
    calendar = planner.plan(args.theme)
    print(planner.summarize(calendar))
    print(f"\nCalendar saved. {len(calendar.entries)} items generated and ready to post.")
    print("Run `python main.py run` to start the agent and publish on schedule.")


def cmd_calendar(args: argparse.Namespace) -> None:
    """Show the current content calendar."""
    from instagram_agent.content_calendar import CALENDAR_FILE, ContentCalendar, ThemePlanner
    if not CALENDAR_FILE.exists():
        print("No calendar found. Create one with:\n  python main.py theme \"Your theme here\"")
        return
    calendar = ContentCalendar.load()
    print(ThemePlanner.summarize(calendar))


def cmd_generate(args: argparse.Namespace) -> None:
    """Generate media files without posting them."""
    config = load_config(args.config)
    _setup_logging(config.log_level, config.log_file)

    from instagram_agent.content_generator import ContentGenerator
    generator = ContentGenerator(config.generation)
    results = generator.generate_batch(
        posts=args.posts,
        stories=args.stories,
        reels=args.reels,
    )
    for kind, paths in results.items():
        for p in paths:
            print(f"  [{kind:7s}] {p}")
    total = sum(len(v) for v in results.values())
    print(f"\nGenerated {total} media files in {config.generation.media_dir}/")


def cmd_brand_kit(args: argparse.Namespace) -> None:
    """Download existing posts from your account as a brand kit."""
    config = load_config(args.config)
    _setup_logging(config.log_level, config.log_file)

    from instagram_agent.client import InstagramClient
    from instagram_agent.brand_kit import BrandKitDownloader

    client = InstagramClient(config.username, config.password)
    client.login()

    downloader = BrandKitDownloader(client.api, config.content.media_dir)
    saved = downloader.download(config.username, count=args.count)

    print(f"\nDownloaded {len(saved)} photos to {downloader.kit_dir}/")
    print("These will now be used as backgrounds when generating content.")
    print("Re-run your theme to regenerate with your photos:")
    print('  python3 main.py theme "Your theme"')


def cmd_flagged(args: argparse.Namespace) -> None:
    """Show or clear flagged accounts."""
    from instagram_agent.engagement import EngagementManager
    if args.clear:
        count = EngagementManager.clear_flagged()
        print(f"Cleared {count} flagged account(s).")
    else:
        print(EngagementManager(
            api=None,
            target_accounts=[],
            discovery_hashtags=[],
        ).show_flagged())


def cmd_run(args: argparse.Namespace) -> None:
    """Start the agent scheduler (daemon or one-shot)."""
    config = load_config(args.config)
    _setup_logging(config.log_level, config.log_file)

    logger = logging.getLogger(__name__)
    logger.info("Loaded configuration from %s", args.config)

    from instagram_agent.scheduler import AgentScheduler
    agent = AgentScheduler(config)

    if args.once:
        agent.run_once()
    else:
        agent.start()


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Instagram Automation Agent",
    )
    sub = parser.add_subparsers(dest="command")

    # -- theme -------------------------------------------------------------
    p_theme = sub.add_parser(
        "theme",
        help="Set a weekly theme and generate a 7-day content calendar",
    )
    p_theme.add_argument("theme", help="The theme for the week (e.g. \"Minimalist productivity\")")
    p_theme.add_argument("--config", default="config.yaml")

    # -- calendar ----------------------------------------------------------
    sub.add_parser("calendar", help="Show the current content calendar")

    # -- generate ----------------------------------------------------------
    p_gen = sub.add_parser("generate", help="Generate media without posting")
    p_gen.add_argument("--posts", type=int, default=1)
    p_gen.add_argument("--stories", type=int, default=1)
    p_gen.add_argument("--reels", type=int, default=0)
    p_gen.add_argument("--config", default="config.yaml")

    # -- brand-kit ---------------------------------------------------------
    p_kit = sub.add_parser("brand-kit", help="Download your existing posts as a brand kit")
    p_kit.add_argument("--count", type=int, default=30, help="Number of recent posts to download")
    p_kit.add_argument("--config", default="config.yaml")

    # -- flagged -----------------------------------------------------------
    p_flag = sub.add_parser("flagged", help="Show or clear flagged accounts")
    p_flag.add_argument("--clear", action="store_true", help="Clear all flagged accounts")

    # -- run ---------------------------------------------------------------
    p_run = sub.add_parser("run", help="Start the agent scheduler")
    p_run.add_argument("--config", default="config.yaml")
    p_run.add_argument("--once", action="store_true", help="Run all jobs once, then exit")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    commands = {
        "theme": cmd_theme,
        "calendar": cmd_calendar,
        "generate": cmd_generate,
        "brand-kit": cmd_brand_kit,
        "flagged": cmd_flagged,
        "run": cmd_run,
    }

    handler = commands.get(args.command)
    if handler is None:
        parser.print_help()
        return

    handler(args)


if __name__ == "__main__":
    main()
