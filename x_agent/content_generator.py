"""Content generation for X (Twitter) — create tweet images, thread
visuals, and media post graphics.

Generated files land in ``media/{tweets,threads,media_posts}/``.
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

from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_PALETTES: list[dict] = [
    {"bg": "#000000", "fg": "#1da1f2"},  # X blue on black
    {"bg": "#15202b", "fg": "#ffffff"},  # X dark theme
    {"bg": "#1a1a2e", "fg": "#e94560"},
    {"bg": "#0f0e17", "fg": "#ff8906"},
    {"bg": "#0d1117", "fg": "#58a6ff"},
    {"bg": "#1e1e1e", "fg": "#00ff88"},
    {"bg": "#2d1b69", "fg": "#e8d44d"},
    {"bg": "#1a1a1a", "fg": "#ff4444"},
]

DEFAULT_QUOTES: list[str] = [
    "Thread incoming. Buckle up.",
    "Most people won't tell you this.",
    "Here's what I learned the hard way.",
    "Unpopular opinion incoming.",
    "Stop scrolling. Read this.",
    "The truth nobody talks about.",
    "I spent 10 years learning this.",
    "This changed my perspective entirely.",
    "Bookmark this for later.",
    "Real talk. No sugarcoating.",
]

TWEET_IMAGE_SIZE = (1200, 675)  # 16:9 for tweet images
THREAD_IMAGE_SIZE = (1200, 675)
MEDIA_POST_SIZE = (1080, 1080)  # Square for engagement

BRAND_KIT_DIR = Path("media/brand_kit")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class GenerationConfig:
    enabled: bool = False
    quotes: List[str] = field(default_factory=lambda: list(DEFAULT_QUOTES))
    palettes: list[dict] = field(default_factory=lambda: list(DEFAULT_PALETTES))
    ai_enabled: bool = False
    openai_api_key: str = ""
    gemini_api_key: str = ""
    ai_prompts: List[str] = field(default_factory=list)
    media_dir: str = "./media"


# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    project_font = Path(__file__).resolve().parent.parent / "fonts" / "LeagueSpartan-Bold.ttf"
    candidates = [
        str(project_font),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Text drawing
# ---------------------------------------------------------------------------

def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    size: tuple[int, int],
    fg_color: tuple[int, int, int],
    font_size: int = 60,
    shadow: bool = False,
) -> None:
    font = _load_font(font_size)
    wrapped = textwrap.fill(text, width=28)
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size[0] - text_w) / 2
    y = (size[1] - text_h) / 2

    if shadow:
        draw.multiline_text(
            (x + 3, y + 3), wrapped, fill=(0, 0, 0), font=font, align="center"
        )

    draw.multiline_text((x, y), wrapped, fill=fg_color, font=font, align="center")


# ---------------------------------------------------------------------------
# Image generation helpers
# ---------------------------------------------------------------------------

def _get_brand_kit_photos() -> list[Path]:
    if not BRAND_KIT_DIR.exists():
        return []
    return sorted(
        p for p in BRAND_KIT_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )


def _center_crop_resize(img: Image.Image, target: tuple[int, int]) -> Image.Image:
    tw, th = target
    iw, ih = img.size
    scale = max(tw / iw, th / ih)
    new_w = int(iw * scale)
    new_h = int(ih * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - tw) // 2
    top = (new_h - th) // 2
    return img.crop((left, top, left + tw, top + th))


def generate_branded_image(
    text: str,
    size: tuple[int, int] = TWEET_IMAGE_SIZE,
    overlay_opacity: float = 0.55,
) -> Optional[Image.Image]:
    photos = _get_brand_kit_photos()
    if not photos:
        return None
    bg_path = random.choice(photos)
    bg = Image.open(bg_path).convert("RGB")
    bg = _center_crop_resize(bg, size)
    dark_overlay = Image.new("RGB", size, (0, 0, 0))
    bg = Image.blend(bg, dark_overlay, overlay_opacity)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=2))
    draw = ImageDraw.Draw(bg)
    font_size = 60 if size[0] >= 1080 else 40
    _draw_centered_text(draw, text, size, (255, 255, 255), font_size, shadow=True)
    return bg


def generate_template_image(
    text: str,
    size: tuple[int, int] = TWEET_IMAGE_SIZE,
    palette: Optional[dict] = None,
) -> Image.Image:
    palette = palette or random.choice(DEFAULT_PALETTES)
    bg = _hex_to_rgb(palette["bg"])
    fg = _hex_to_rgb(palette["fg"])
    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)
    font_size = 60 if size[0] >= 1080 else 40
    _draw_centered_text(draw, text, size, fg, font_size)
    return img


def generate_image(
    text: str,
    size: tuple[int, int] = TWEET_IMAGE_SIZE,
    palette: Optional[dict] = None,
) -> Image.Image:
    branded = generate_branded_image(text, size)
    if branded is not None:
        return branded
    return generate_template_image(text, size, palette)


# ---------------------------------------------------------------------------
# High-level generator
# ---------------------------------------------------------------------------

class ContentGenerator:
    """Generate media files for X (Twitter) content."""

    def __init__(self, config: GenerationConfig) -> None:
        self._cfg = config
        self._media_dir = Path(config.media_dir)

    def _ensure_dirs(self) -> None:
        for sub in ("tweets", "threads", "media_posts"):
            (self._media_dir / sub).mkdir(parents=True, exist_ok=True)

    def generate_tweet_image(self, text: Optional[str] = None) -> Path:
        self._ensure_dirs()
        text = text or random.choice(self._cfg.quotes)
        img = generate_image(text, TWEET_IMAGE_SIZE)
        fname = f"tweet_{uuid.uuid4().hex[:8]}.png"
        path = self._media_dir / "tweets" / fname
        img.save(str(path))
        caption_path = path.with_suffix(".txt")
        caption_path.write_text(text)
        logger.info("Generated tweet image: %s", path)
        return path

    def generate_thread_image(self, text: Optional[str] = None) -> Path:
        self._ensure_dirs()
        text = text or random.choice(self._cfg.quotes)
        img = generate_image(text, THREAD_IMAGE_SIZE)
        fname = f"thread_{uuid.uuid4().hex[:8]}.png"
        path = self._media_dir / "threads" / fname
        img.save(str(path))
        caption_path = path.with_suffix(".txt")
        caption_path.write_text(text)
        logger.info("Generated thread image: %s", path)
        return path

    def generate_media_post(self, text: Optional[str] = None) -> Path:
        self._ensure_dirs()
        text = text or random.choice(self._cfg.quotes)
        img = generate_image(text, MEDIA_POST_SIZE)
        fname = f"media_{uuid.uuid4().hex[:8]}.png"
        path = self._media_dir / "media_posts" / fname
        img.save(str(path))
        caption_path = path.with_suffix(".txt")
        caption_path.write_text(text)
        logger.info("Generated media post: %s", path)
        return path

    def generate_batch(
        self,
        tweets: int = 1,
        threads: int = 1,
        media_posts: int = 0,
    ) -> dict[str, list[Path]]:
        results: dict[str, list[Path]] = {
            "tweets": [], "threads": [], "media_posts": [],
        }
        for _ in range(tweets):
            results["tweets"].append(self.generate_tweet_image())
        for _ in range(threads):
            results["threads"].append(self.generate_thread_image())
        for _ in range(media_posts):
            results["media_posts"].append(self.generate_media_post())
        total = sum(len(v) for v in results.values())
        logger.info("Generated %d total media files", total)
        return results
