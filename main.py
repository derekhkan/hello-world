#!/usr/bin/env python3
"""Entry point for the Instagram Automation Agent.

Usage
-----
Run on a schedule (daemon mode)::

    python main.py --config config.yaml

Execute every job once and exit::

    python main.py --config config.yaml --once

"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from instagram_agent.config import load_config
from instagram_agent.scheduler import AgentScheduler


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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Instagram Automation Agent"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to the YAML configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run every job once immediately, then exit.",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    _setup_logging(config.log_level, config.log_file)

    logger = logging.getLogger(__name__)
    logger.info("Loaded configuration from %s", args.config)

    agent = AgentScheduler(config)

    if args.once:
        agent.run_once()
    else:
        agent.start()


if __name__ == "__main__":
    main()
