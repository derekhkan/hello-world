"""Bot orchestrator — ties content generation, image creation, video assembly,
and YouTube upload into a single automated pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from yt_shorts_bot.config import Settings, load_settings
from yt_shorts_bot.content.generator import Script, generate_script, load_custom_theme
from yt_shorts_bot.images.midjourney import generate_images_for_script
from yt_shorts_bot.video.assembler import assemble_video
from yt_shorts_bot.youtube.uploader import upload_video

logger = logging.getLogger(__name__)


class ShortsBot:
    """End-to-end YouTube Shorts creation and publishing bot."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or load_settings()

    def _run_dir(self) -> Path:
        """Create a timestamped directory for this run's artifacts."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = self.settings.output_dir / ts
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    def generate_script(
        self,
        theme: str = "nano_banana",
        num_scenes: int = 5,
        custom_theme_path: Optional[Path] = None,
        custom_vars: Optional[dict] = None,
    ) -> Script:
        """Step 1: Generate a content script."""
        if custom_theme_path:
            load_custom_theme(custom_theme_path)
            theme = custom_theme_path.stem

        script = generate_script(theme, num_scenes, custom_vars)
        logger.info(
            "Generated script: '%s' (%d scenes, ~%.0f s)",
            script.title,
            len(script.scenes),
            script.total_duration,
        )
        return script

    async def generate_images(self, script: Script, run_dir: Path) -> list[Path]:
        """Step 2: Generate images for each scene."""
        images_dir = run_dir / "images"
        images_dir.mkdir(exist_ok=True)
        paths = await generate_images_for_script(script, images_dir)
        logger.info("Generated %d images in %s", len(paths), images_dir)
        return paths

    async def assemble(
        self,
        script: Script,
        image_paths: list[Path],
        run_dir: Path,
        background_music: Optional[Path] = None,
    ) -> Path:
        """Step 3: Assemble images + TTS into a video."""
        video_path = run_dir / "short.mp4"
        await assemble_video(
            image_paths,
            script.scenes,
            video_path,
            background_music=background_music,
            settings=self.settings.video,
        )
        return video_path

    def publish(self, video_path: Path, script: Script) -> str:
        """Step 4: Upload to YouTube."""
        video_id = upload_video(
            video_path,
            title=script.title,
            description=script.description,
            tags=script.tags,
            settings=self.settings.youtube,
        )
        return video_id

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    async def run(
        self,
        theme: str = "nano_banana",
        num_scenes: int = 5,
        custom_theme_path: Optional[Path] = None,
        custom_vars: Optional[dict] = None,
        background_music: Optional[Path] = None,
        skip_upload: bool = False,
    ) -> dict:
        """Run the full pipeline: script → images → video → upload.

        Parameters
        ----------
        theme:
            Theme name (built-in or from a custom YAML).
        num_scenes:
            Number of middle scenes.
        custom_theme_path:
            Path to a custom theme YAML file.
        custom_vars:
            Extra template variables.
        background_music:
            Optional background music file.
        skip_upload:
            If True, skip the YouTube upload step (useful for testing).

        Returns
        -------
        Dict with keys: ``script``, ``images``, ``video``, ``video_id``, ``run_dir``.
        """
        run_dir = self._run_dir()
        logger.info("Run directory: %s", run_dir)

        # 1. Script
        script = self.generate_script(theme, num_scenes, custom_theme_path, custom_vars)
        script.save(run_dir / "script.json")

        # 2. Images
        image_paths = await self.generate_images(script, run_dir)

        # 3. Video
        video_path = await self.assemble(script, image_paths, run_dir, background_music)

        # 4. Upload
        video_id = None
        if not skip_upload:
            video_id = self.publish(video_path, script)

        result = {
            "script": script,
            "images": image_paths,
            "video": video_path,
            "video_id": video_id,
            "run_dir": run_dir,
        }

        logger.info("Pipeline complete! Results: %s", {k: str(v) for k, v in result.items()})
        return result
