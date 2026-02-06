#!/usr/bin/env python3
"""Entry point for the X (Twitter) Automation Agent.

Usage
-----
Set a weekly theme and generate a 7-day content calendar::

    python main_x.py theme "Staying Disciplined"

View the current calendar::

    python main_x.py calendar

Run on a schedule (daemon mode)::

    python main_x.py run --config x_config.yaml

Execute every job once and exit::

    python main_x.py run --config x_config.yaml --once

Generate a batch of tweet images / thread visuals without posting::

    python main_x.py generate --tweets 3 --threads 2 --media-posts 1
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from x_agent.config import load_config

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

    from x_agent.content_calendar import ThemePlanner
    planner = ThemePlanner(config.generation)
    calendar = planner.plan(args.theme)
    print(planner.summarize(calendar))
    print(f"\nCalendar saved. {len(calendar.entries)} items generated and ready to publish.")
    print("Run `python main_x.py run` to start the agent and publish on schedule.")


def cmd_calendar(args: argparse.Namespace) -> None:
    """Show the current content calendar."""
    from x_agent.content_calendar import CALENDAR_FILE, ContentCalendar, ThemePlanner
    if not CALENDAR_FILE.exists():
        print("No calendar found. Create one with:\n  python main_x.py theme \"Your theme here\"")
        return
    calendar = ContentCalendar.load()
    print(ThemePlanner.summarize(calendar))


def cmd_generate(args: argparse.Namespace) -> None:
    """Generate media files without posting them."""
    config = load_config(args.config)
    _setup_logging(config.log_level, config.log_file)

    from x_agent.content_generator import ContentGenerator
    generator = ContentGenerator(config.generation)
    results = generator.generate_batch(
        tweets=args.tweets,
        threads=args.threads,
        media_posts=args.media_posts,
    )
    for kind, paths in results.items():
        for p in paths:
            print(f"  [{kind:11s}] {p}")
    total = sum(len(v) for v in results.values())
    print(f"\nGenerated {total} media files in {config.generation.media_dir}/")


def cmd_flagged(args: argparse.Namespace) -> None:
    """Show or clear flagged accounts."""
    from x_agent.engagement import EngagementManager
    if args.clear:
        count = EngagementManager.clear_flagged()
        print(f"Cleared {count} flagged account(s).")
    else:
        print(EngagementManager(
            api=None,
            target_accounts=[],
            discovery_keywords=[],
        ).show_flagged())


def cmd_run(args: argparse.Namespace) -> None:
    """Start the agent scheduler (daemon or one-shot)."""
    config = load_config(args.config)
    _setup_logging(config.log_level, config.log_file)

    logger = logging.getLogger(__name__)
    logger.info("Loaded configuration from %s", args.config)

    from x_agent.scheduler import AgentScheduler
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
        description="X (Twitter) Automation Agent",
    )
    sub = parser.add_subparsers(dest="command")

    # -- theme -------------------------------------------------------------
    p_theme = sub.add_parser(
        "theme",
        help="Set a weekly theme and generate a 7-day content calendar",
    )
    p_theme.add_argument("theme", help="The theme for the week")
    p_theme.add_argument("--config", default="x_config.yaml")

    # -- calendar ----------------------------------------------------------
    sub.add_parser("calendar", help="Show the current content calendar")

    # -- generate ----------------------------------------------------------
    p_gen = sub.add_parser("generate", help="Generate media without posting")
    p_gen.add_argument("--tweets", type=int, default=1)
    p_gen.add_argument("--threads", type=int, default=1)
    p_gen.add_argument("--media-posts", type=int, default=0, dest="media_posts")
    p_gen.add_argument("--config", default="x_config.yaml")

    # -- flagged -----------------------------------------------------------
    p_flag = sub.add_parser("flagged", help="Show or clear flagged accounts")
    p_flag.add_argument("--clear", action="store_true", help="Clear all flagged accounts")

    # -- run ---------------------------------------------------------------
    p_run = sub.add_parser("run", help="Start the agent scheduler")
    p_run.add_argument("--config", default="x_config.yaml")
    p_run.add_argument("--once", action="store_true", help="Run all jobs once, then exit")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    commands = {
        "theme": cmd_theme,
        "calendar": cmd_calendar,
        "generate": cmd_generate,
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
