"""Content generation — create images, stories, and video reels
programmatically.

Two modes of operation:

1. **Template mode** (default, no API key required)
   Uses Pillow to render text-on-background graphics from a pool of quotes,
   colours, and fonts.

2. **AI mode** (requires an OpenAI API key)
   Calls DALL-E to generate images from text prompts.

Generated files are placed into the appropriate ``media/`` subdirectory so
the ``ContentManager`` picks them up on the next scheduled publish.
"""

from __future__ import annotations

import logging
import os
import random
import textwrap
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_PALETTES: list[dict] = [
    {"bg": "#1a1a2e", "fg": "#e94560"},
    {"bg": "#16213e", "fg": "#0f3460"},
    {"bg": "#0f0e17", "fg": "#ff8906"},
    {"bg": "#232946", "fg": "#eebbc3"},
    {"bg": "#004643", "fg": "#f9bc60"},
    {"bg": "#271c19", "fg": "#ffc0ad"},
    {"bg": "#fef6e4", "fg": "#001858"},
    {"bg": "#f2f7f5", "fg": "#00473e"},
]

DEFAULT_QUOTES: list[str] = [
    "Create the things you wish existed.",
    "Stay hungry. Stay foolish.",
    "The best time to start was yesterday. The next best time is now.",
    "Do something today that your future self will thank you for.",
    "Make it simple, but significant.",
    "Dream big. Start small. Act now.",
    "Your vibe attracts your tribe.",
    "Less perfection, more authenticity.",
    "Good things take time.",
    "Be the energy you want to attract.",
]

POST_SIZE = (1080, 1080)
STORY_SIZE = (1080, 1920)
REEL_SIZE = (1080, 1920)


# ---------------------------------------------------------------------------
# Data classes for generation config
# ---------------------------------------------------------------------------

@dataclass
class GenerationConfig:
    enabled: bool = False
    # Template settings
    quotes: List[str] = field(default_factory=lambda: list(DEFAULT_QUOTES))
    palettes: list[dict] = field(default_factory=lambda: list(DEFAULT_PALETTES))
    # AI generation (DALL-E)
    ai_enabled: bool = False
    openai_api_key: str = ""
    ai_prompts: List[str] = field(default_factory=list)
    # Where to place generated files
    media_dir: str = "./media"


# ---------------------------------------------------------------------------
# Template-based image generator
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load a TrueType font; fall back to the built-in bitmap font."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    size: tuple[int, int],
    fg_color: tuple[int, int, int],
    font_size: int = 60,
) -> None:
    """Word-wrap *text* and draw it centered on the canvas."""
    font = _load_font(font_size)
    wrapped = textwrap.fill(text, width=22)
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size[0] - text_w) / 2
    y = (size[1] - text_h) / 2
    draw.multiline_text((x, y), wrapped, fill=fg_color, font=font, align="center")


def generate_template_image(
    text: str,
    size: tuple[int, int] = POST_SIZE,
    palette: Optional[dict] = None,
) -> Image.Image:
    """Return a Pillow ``Image`` with *text* rendered on a coloured background."""
    palette = palette or random.choice(DEFAULT_PALETTES)
    bg = _hex_to_rgb(palette["bg"])
    fg = _hex_to_rgb(palette["fg"])

    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)

    font_size = 60 if size[0] >= 1080 else 40
    _draw_centered_text(draw, text, size, fg, font_size)

    return img


# ---------------------------------------------------------------------------
# AI-based image generator (DALL-E)
# ---------------------------------------------------------------------------

def generate_ai_image(
    prompt: str,
    api_key: str,
    size: str = "1024x1024",
    output_path: Optional[Path] = None,
) -> Path:
    """Call the OpenAI DALL-E API and save the resulting image.

    Returns the path to the saved image file.
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "The 'openai' package is required for AI image generation. "
            "Install it with: pip install openai"
        )

    client = OpenAI(api_key=api_key)
    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size=size,
        quality="standard",
        n=1,
    )

    image_url = response.data[0].url

    # Download the image
    import urllib.request
    if output_path is None:
        output_path = Path(f"/tmp/dalle_{uuid.uuid4().hex[:8]}.png")

    urllib.request.urlretrieve(image_url, str(output_path))
    logger.info("AI image saved to %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Video reel generator (slideshow from images)
# ---------------------------------------------------------------------------

def generate_slideshow_reel(
    texts: List[str],
    output_path: Path,
    duration_per_slide: float = 3.0,
    fps: int = 24,
    size: tuple[int, int] = REEL_SIZE,
    palettes: Optional[list[dict]] = None,
) -> Path:
    """Create a simple slideshow video from a list of text slides.

    Each slide is rendered as a template image and held for
    *duration_per_slide* seconds. The result is an ``.mp4`` file.
    """
    try:
        from moviepy.editor import ImageClip, concatenate_videoclips
    except ImportError:
        raise ImportError(
            "The 'moviepy' package is required for reel generation. "
            "Install it with: pip install moviepy"
        )

    palettes = palettes or DEFAULT_PALETTES
    clips = []
    for i, text in enumerate(texts):
        palette = palettes[i % len(palettes)]
        img = generate_template_image(text, size=size, palette=palette)
        # moviepy works with numpy arrays
        import numpy as np
        arr = np.array(img)
        clip = ImageClip(arr, duration=duration_per_slide)
        clips.append(clip)

    video = concatenate_videoclips(clips, method="compose")
    video.write_videofile(
        str(output_path), fps=fps, codec="libx264", audio=False, logger=None
    )
    logger.info("Reel saved to %s (%.1fs)", output_path, video.duration)
    return output_path


# ---------------------------------------------------------------------------
# High-level generator that produces ready-to-publish files
# ---------------------------------------------------------------------------

class ContentGenerator:
    """Generate media files and drop them into ``media/`` for publishing."""

    def __init__(self, config: GenerationConfig) -> None:
        self._cfg = config
        self._media_dir = Path(config.media_dir)

    def _ensure_dirs(self) -> None:
        for sub in ("posts", "reels", "stories"):
            (self._media_dir / sub).mkdir(parents=True, exist_ok=True)

    # -- Posts -------------------------------------------------------------

    def generate_post(self, text: Optional[str] = None) -> Path:
        """Create a single post image and save it to ``media/posts/``."""
        self._ensure_dirs()
        text = text or random.choice(self._cfg.quotes)
        img = generate_template_image(text, POST_SIZE)
        fname = f"post_{uuid.uuid4().hex[:8]}.png"
        path = self._media_dir / "posts" / fname
        img.save(str(path))

        # Write sidecar caption
        caption_path = path.with_suffix(".txt")
        caption_path.write_text(text)

        logger.info("Generated post: %s", path)
        return path

    def generate_ai_post(self, prompt: Optional[str] = None) -> Path:
        """Generate a post image using DALL-E."""
        self._ensure_dirs()
        if not self._cfg.openai_api_key:
            raise ValueError("OpenAI API key is required for AI generation")
        prompt = prompt or random.choice(self._cfg.ai_prompts or ["A beautiful photograph"])
        fname = f"ai_post_{uuid.uuid4().hex[:8]}.png"
        path = self._media_dir / "posts" / fname
        generate_ai_image(prompt, self._cfg.openai_api_key, output_path=path)

        caption_path = path.with_suffix(".txt")
        caption_path.write_text(prompt)
        return path

    # -- Stories -----------------------------------------------------------

    def generate_story(self, text: Optional[str] = None) -> Path:
        """Create a story graphic (1080x1920) and save it to ``media/stories/``."""
        self._ensure_dirs()
        text = text or random.choice(self._cfg.quotes)
        img = generate_template_image(text, STORY_SIZE)
        fname = f"story_{uuid.uuid4().hex[:8]}.png"
        path = self._media_dir / "stories" / fname
        img.save(str(path))
        logger.info("Generated story: %s", path)
        return path

    # -- Reels -------------------------------------------------------------

    def generate_reel(
        self,
        texts: Optional[List[str]] = None,
        slides: int = 4,
    ) -> Path:
        """Create a short slideshow reel from quotes."""
        self._ensure_dirs()
        if texts is None:
            texts = random.sample(
                self._cfg.quotes, min(slides, len(self._cfg.quotes))
            )
        fname = f"reel_{uuid.uuid4().hex[:8]}.mp4"
        path = self._media_dir / "reels" / fname
        generate_slideshow_reel(texts, path, palettes=self._cfg.palettes)

        caption_path = path.with_suffix(".txt")
        caption_path.write_text(" | ".join(texts))

        logger.info("Generated reel: %s", path)
        return path

    # -- Batch -------------------------------------------------------------

    def generate_batch(
        self,
        posts: int = 1,
        stories: int = 1,
        reels: int = 0,
    ) -> dict[str, list[Path]]:
        """Generate a batch of content across all types."""
        results: dict[str, list[Path]] = {"posts": [], "stories": [], "reels": []}

        for _ in range(posts):
            results["posts"].append(self.generate_post())
        for _ in range(stories):
            results["stories"].append(self.generate_story())
        for _ in range(reels):
            results["reels"].append(self.generate_reel())

        total = sum(len(v) for v in results.values())
        logger.info("Generated %d total media files", total)
        return results
