"""CLI entry point for the YouTube Shorts Bot.

Usage:
    yt-shorts-bot generate               # generate script + images + video (no upload)
    yt-shorts-bot generate --upload       # generate and upload
    yt-shorts-bot upload <video_path>     # upload an existing video
    yt-shorts-bot themes                  # list available themes
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import click

from yt_shorts_bot.config import load_settings


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.option("--log-level", default="INFO", help="Logging level")
def main(log_level: str) -> None:
    """YouTube Shorts Bot — generate AI videos and publish them automatically."""
    _setup_logging(log_level)


@main.command()
@click.option("--theme", default="nano_banana", help="Content theme name")
@click.option("--scenes", default=5, help="Number of middle scenes (1-8)")
@click.option("--custom-theme", type=click.Path(exists=True), default=None, help="Custom theme YAML")
@click.option("--music", type=click.Path(exists=True), default=None, help="Background music file")
@click.option("--upload/--no-upload", default=False, help="Upload to YouTube after generating")
@click.option("--var", multiple=True, help="Custom variable KEY=VALUE (repeatable)")
def generate(
    theme: str,
    scenes: int,
    custom_theme: Optional[str],
    music: Optional[str],
    upload: bool,
    var: tuple[str, ...],
) -> None:
    """Generate a YouTube Short from scratch."""
    from yt_shorts_bot.bot import ShortsBot

    custom_vars = {}
    for v in var:
        if "=" in v:
            k, val = v.split("=", 1)
            custom_vars[k] = val

    bot = ShortsBot()
    result = asyncio.run(
        bot.run(
            theme=theme,
            num_scenes=scenes,
            custom_theme_path=Path(custom_theme) if custom_theme else None,
            custom_vars=custom_vars or None,
            background_music=Path(music) if music else None,
            skip_upload=not upload,
        )
    )

    click.echo(f"\nScript: {result['run_dir'] / 'script.json'}")
    click.echo(f"Video:  {result['video']}")
    if result["video_id"]:
        click.echo(f"YouTube: https://youtube.com/shorts/{result['video_id']}")
    else:
        click.echo("(Upload skipped — use --upload to publish)")


@main.command()
@click.argument("video_path", type=click.Path(exists=True))
@click.option("--title", required=True, help="Video title")
@click.option("--description", default="", help="Video description")
@click.option("--tags", default="", help="Comma-separated tags")
@click.option("--privacy", default="public", type=click.Choice(["public", "unlisted", "private"]))
def upload(video_path: str, title: str, description: str, tags: str, privacy: str) -> None:
    """Upload an existing video to YouTube as a Short."""
    from yt_shorts_bot.youtube.uploader import upload_video
    from yt_shorts_bot.config import load_settings

    settings = load_settings().youtube
    settings.privacy_status = privacy

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    video_id = upload_video(
        Path(video_path),
        title=title,
        description=description,
        tags=tag_list,
        settings=settings,
    )
    click.echo(f"Uploaded! https://youtube.com/shorts/{video_id}")


@main.command()
def themes() -> None:
    """List available content themes."""
    from yt_shorts_bot.content.generator import THEMES

    click.echo("Available themes:\n")
    for key, theme in THEMES.items():
        name = theme.get("name", key)
        num_scenes = len(theme.get("scene_templates", []))
        hooks = len(theme.get("hook_templates", []))
        click.echo(f"  {key:20s}  {name} ({num_scenes} scenes, {hooks} hooks)")


@main.command()
def script_only() -> None:
    """Generate and print a script without creating images or video."""
    from yt_shorts_bot.content.generator import generate_script
    import json

    script = generate_script()
    click.echo(json.dumps(script.to_dict(), indent=2))


if __name__ == "__main__":
    main()
