"""Content generation for LinkedIn — create post images, article covers,
and carousel slides.

Generated files land in ``media/{posts,articles,carousels}/``.
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
    {"bg": "#0077b5", "fg": "#ffffff"},  # LinkedIn blue
    {"bg": "#1a1a2e", "fg": "#e94560"},
    {"bg": "#004182", "fg": "#ffffff"},  # Darker LinkedIn
    {"bg": "#0d1117", "fg": "#58a6ff"},
    {"bg": "#283e4a", "fg": "#ffffff"},  # LinkedIn dark
    {"bg": "#1e3a5f", "fg": "#f0c040"},
    {"bg": "#2d1b69", "fg": "#e8d44d"},
    {"bg": "#f3f2ef", "fg": "#000000"},  # LinkedIn light theme
]

DEFAULT_QUOTES: list[str] = [
    "Your network is your net worth.",
    "The best investment is in yourself.",
    "Leadership isn't about titles. It's about impact.",
    "Great leaders create more leaders, not followers.",
    "Culture eats strategy for breakfast.",
    "Success leaves clues. Pay attention.",
    "Your career is a marathon, not a sprint.",
    "The best time to plant a tree was 20 years ago. The second best time is now.",
    "Be so good they can't ignore you.",
    "Hard work compounds. So does knowledge.",
]

POST_IMAGE_SIZE = (1200, 628)   # LinkedIn recommended
ARTICLE_COVER_SIZE = (1200, 628)
CAROUSEL_SLIDE_SIZE = (1080, 1080)

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
    font_size: int = 56,
    shadow: bool = False,
) -> None:
    font = _load_font(font_size)
    wrapped = textwrap.fill(text, width=30)
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
    size: tuple[int, int] = POST_IMAGE_SIZE,
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
    font_size = 56 if size[0] >= 1080 else 36
    _draw_centered_text(draw, text, size, (255, 255, 255), font_size, shadow=True)
    return bg


def generate_template_image(
    text: str,
    size: tuple[int, int] = POST_IMAGE_SIZE,
    palette: Optional[dict] = None,
) -> Image.Image:
    palette = palette or random.choice(DEFAULT_PALETTES)
    bg = _hex_to_rgb(palette["bg"])
    fg = _hex_to_rgb(palette["fg"])
    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)
    font_size = 56 if size[0] >= 1080 else 36
    _draw_centered_text(draw, text, size, fg, font_size)
    return img


def generate_image(
    text: str,
    size: tuple[int, int] = POST_IMAGE_SIZE,
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
    """Generate media files for LinkedIn content."""

    def __init__(self, config: GenerationConfig) -> None:
        self._cfg = config
        self._media_dir = Path(config.media_dir)

    def _ensure_dirs(self) -> None:
        for sub in ("posts", "articles", "carousels"):
            (self._media_dir / sub).mkdir(parents=True, exist_ok=True)

    def generate_post_image(self, text: Optional[str] = None) -> Path:
        self._ensure_dirs()
        text = text or random.choice(self._cfg.quotes)
        img = generate_image(text, POST_IMAGE_SIZE)
        fname = f"post_{uuid.uuid4().hex[:8]}.png"
        path = self._media_dir / "posts" / fname
        img.save(str(path))
        caption_path = path.with_suffix(".txt")
        caption_path.write_text(text)
        logger.info("Generated post image: %s", path)
        return path

    def generate_article_cover(self, text: Optional[str] = None) -> Path:
        self._ensure_dirs()
        text = text or random.choice(self._cfg.quotes)
        img = generate_image(text, ARTICLE_COVER_SIZE)
        fname = f"article_{uuid.uuid4().hex[:8]}.png"
        path = self._media_dir / "articles" / fname
        img.save(str(path))
        caption_path = path.with_suffix(".txt")
        caption_path.write_text(text)
        logger.info("Generated article cover: %s", path)
        return path

    def generate_carousel_slide(self, text: Optional[str] = None) -> Path:
        self._ensure_dirs()
        text = text or random.choice(self._cfg.quotes)
        img = generate_image(text, CAROUSEL_SLIDE_SIZE)
        fname = f"carousel_{uuid.uuid4().hex[:8]}.png"
        path = self._media_dir / "carousels" / fname
        img.save(str(path))
        caption_path = path.with_suffix(".txt")
        caption_path.write_text(text)
        logger.info("Generated carousel slide: %s", path)
        return path

    def generate_batch(
        self,
        posts: int = 1,
        articles: int = 0,
        carousels: int = 0,
    ) -> dict[str, list[Path]]:
        results: dict[str, list[Path]] = {
            "posts": [], "articles": [], "carousels": [],
        }
        for _ in range(posts):
            results["posts"].append(self.generate_post_image())
        for _ in range(articles):
            results["articles"].append(self.generate_article_cover())
        for _ in range(carousels):
            results["carousels"].append(self.generate_carousel_slide())
        total = sum(len(v) for v in results.values())
        logger.info("Generated %d total media files", total)
        return results
