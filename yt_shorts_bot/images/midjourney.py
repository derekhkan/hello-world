"""Midjourney image generation client.

Supports both the official Midjourney API and popular third-party proxy APIs
(e.g. GoAPI, ImagineAPI, etc.) that expose a compatible REST interface.

Workflow:
  1. Submit an /imagine job with the prompt.
  2. Poll for completion.
  3. Download the result image(s).

If no API key is configured, falls back to placeholder images so the rest of
the pipeline can still be tested locally.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

import httpx
from PIL import Image, ImageDraw, ImageFont

from yt_shorts_bot.config import MidjourneySettings, load_settings

logger = logging.getLogger(__name__)


class MidjourneyClient:
    """Async client for Midjourney-compatible image generation APIs."""

    def __init__(self, settings: Optional[MidjourneySettings] = None) -> None:
        self.settings = settings or load_settings().midjourney
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.settings.api_url,
                headers={"Authorization": f"Bearer {self.settings.api_key}"},
                timeout=self.settings.timeout,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Core workflow
    # ------------------------------------------------------------------

    async def generate(self, prompt: str, output_path: Path) -> Path:
        """Generate an image from *prompt* and save to *output_path*.

        Returns the path to the saved image.
        """
        full_prompt = f"{prompt} {self.settings.default_params}".strip()

        if not self.settings.api_key:
            logger.warning("No Midjourney API key — generating placeholder image")
            return self._make_placeholder(full_prompt, output_path)

        client = await self._get_client()

        # Step 1 — submit imagine job
        logger.info("Submitting imagine job: %s", full_prompt[:100])
        resp = await client.post(
            "/v1/imagine",
            json={"prompt": full_prompt},
        )
        resp.raise_for_status()
        job = resp.json()
        job_id = job["taskId"]

        # Step 2 — poll until done
        image_url = await self._poll_job(client, job_id)

        # Step 3 — download
        return await self._download(client, image_url, output_path)

    async def _poll_job(self, client: httpx.AsyncClient, job_id: str) -> str:
        """Poll the job endpoint until an image URL is available."""
        deadline = time.monotonic() + self.settings.timeout
        while time.monotonic() < deadline:
            resp = await client.get(f"/v1/task/{job_id}")
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "")
            if status == "completed":
                return data["imageUrl"]
            if status == "failed":
                raise RuntimeError(f"Midjourney job {job_id} failed: {data}")
            await asyncio.sleep(5)
        raise TimeoutError(f"Midjourney job {job_id} timed out")

    async def _download(self, client: httpx.AsyncClient, url: str, dest: Path) -> Path:
        """Download an image from *url* to *dest*."""
        resp = await client.get(url)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        logger.info("Saved image to %s", dest)
        return dest

    # ------------------------------------------------------------------
    # Placeholder for local/offline testing
    # ------------------------------------------------------------------

    @staticmethod
    def _make_placeholder(prompt: str, output_path: Path) -> Path:
        """Create a simple placeholder image with the prompt text."""
        width, height = 1080, 1920
        img = Image.new("RGB", (width, height), color=(20, 20, 30))
        draw = ImageDraw.Draw(img)

        # Wrap prompt text
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
        except OSError:
            font = ImageFont.load_default()

        margin = 60
        max_chars_per_line = 35
        lines = []
        words = prompt.split()
        current_line = ""
        for word in words:
            if len(current_line) + len(word) + 1 <= max_chars_per_line:
                current_line = f"{current_line} {word}".strip()
            else:
                lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)

        y = height // 2 - len(lines) * 20
        for line in lines:
            draw.text((margin, y), line, fill=(200, 200, 255), font=font)
            y += 40

        # Label
        draw.text((margin, 80), "[PLACEHOLDER]", fill=(255, 200, 0), font=font)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "PNG")
        logger.info("Saved placeholder image to %s", output_path)
        return output_path


async def generate_images_for_script(script, output_dir: Path) -> list[Path]:
    """Generate one image per scene and return the list of image paths.

    Parameters
    ----------
    script:
        A ``Script`` instance from the content generator.
    output_dir:
        Directory to save images into.
    """
    from yt_shorts_bot.content.generator import Script  # avoid circular import

    client = MidjourneyClient()
    paths: list[Path] = []
    try:
        for i, scene in enumerate(script.scenes):
            dest = output_dir / f"scene_{i:03d}.png"
            path = await client.generate(scene.image_prompt, dest)
            paths.append(path)
    finally:
        await client.close()
    return paths
