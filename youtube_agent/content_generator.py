"""Content generation for YouTube — create thumbnails, shorts, and
community post images.

Modes of operation (tried in order):

1. **Gemini mode** — generates photorealistic images via Gemini API,
   then overlays text for thumbnails.

2. **Brand kit mode** — uses your own downloaded thumbnails as
   backgrounds with a dark overlay and text on top.

3. **Template mode** (fallback) — renders text on a solid-colour
   background using Pillow.

Generated files land in ``media/{thumbnails,shorts,community}/``.
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
    {"bg": "#ff0000", "fg": "#ffffff"},  # YouTube red
    {"bg": "#1a1a2e", "fg": "#e94560"},
    {"bg": "#0f0e17", "fg": "#ff8906"},
    {"bg": "#282828", "fg": "#ffffff"},
    {"bg": "#1e3a5f", "fg": "#f0c040"},
    {"bg": "#0d1117", "fg": "#58a6ff"},
    {"bg": "#2d1b69", "fg": "#e8d44d"},
    {"bg": "#1a1a1a", "fg": "#ff4444"},
]

DEFAULT_QUOTES: list[str] = [
    "Subscribe for more content like this.",
    "Drop a comment if you agree.",
    "This changed everything for me.",
    "Watch until the end — you won't believe it.",
    "Here's what nobody tells you.",
    "Stop scrolling. This is important.",
    "I wish I knew this sooner.",
    "The truth about consistency.",
    "Most people get this wrong.",
    "Let me break this down for you.",
]

THUMBNAIL_SIZE = (1280, 720)
SHORTS_SIZE = (1080, 1920)
COMMUNITY_SIZE = (1080, 1080)

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
    font_size: int = 72,
    shadow: bool = False,
) -> None:
    """Word-wrap *text* and draw it centered on the canvas."""
    font = _load_font(font_size)
    wrapped = textwrap.fill(text, width=20)
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
# Brand kit image
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
    size: tuple[int, int] = THUMBNAIL_SIZE,
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
    font_size = 72 if size[0] >= 1080 else 48
    _draw_centered_text(draw, text, size, (255, 255, 255), font_size, shadow=True)
    return bg


# ---------------------------------------------------------------------------
# Template-based (solid colour background)
# ---------------------------------------------------------------------------

def generate_template_image(
    text: str,
    size: tuple[int, int] = THUMBNAIL_SIZE,
    palette: Optional[dict] = None,
) -> Image.Image:
    palette = palette or random.choice(DEFAULT_PALETTES)
    bg = _hex_to_rgb(palette["bg"])
    fg = _hex_to_rgb(palette["fg"])
    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)
    font_size = 72 if size[0] >= 1080 else 48
    _draw_centered_text(draw, text, size, fg, font_size)
    return img


# ---------------------------------------------------------------------------
# Smart image generator — brand kit → template fallback
# ---------------------------------------------------------------------------

def generate_image(
    text: str,
    size: tuple[int, int] = THUMBNAIL_SIZE,
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
    """Generate media files for YouTube content."""

    def __init__(self, config: GenerationConfig) -> None:
        self._cfg = config
        self._media_dir = Path(config.media_dir)

    def _ensure_dirs(self) -> None:
        for sub in ("thumbnails", "shorts", "community"):
            (self._media_dir / sub).mkdir(parents=True, exist_ok=True)

    def generate_thumbnail(self, text: Optional[str] = None) -> Path:
        self._ensure_dirs()
        text = text or random.choice(self._cfg.quotes)
        img = generate_image(text, THUMBNAIL_SIZE)
        fname = f"thumb_{uuid.uuid4().hex[:8]}.png"
        path = self._media_dir / "thumbnails" / fname
        img.save(str(path))
        caption_path = path.with_suffix(".txt")
        caption_path.write_text(text)
        logger.info("Generated thumbnail: %s", path)
        return path

    def generate_short_thumbnail(self, text: Optional[str] = None) -> Path:
        self._ensure_dirs()
        text = text or random.choice(self._cfg.quotes)
        img = generate_image(text, SHORTS_SIZE)
        fname = f"short_thumb_{uuid.uuid4().hex[:8]}.png"
        path = self._media_dir / "shorts" / fname
        img.save(str(path))
        caption_path = path.with_suffix(".txt")
        caption_path.write_text(text)
        logger.info("Generated short thumbnail: %s", path)
        return path

    def generate_community_image(self, text: Optional[str] = None) -> Path:
        self._ensure_dirs()
        text = text or random.choice(self._cfg.quotes)
        img = generate_image(text, COMMUNITY_SIZE)
        fname = f"community_{uuid.uuid4().hex[:8]}.png"
        path = self._media_dir / "community" / fname
        img.save(str(path))
        caption_path = path.with_suffix(".txt")
        caption_path.write_text(text)
        logger.info("Generated community image: %s", path)
        return path

    def generate_batch(
        self,
        thumbnails: int = 1,
        shorts: int = 1,
        community: int = 0,
    ) -> dict[str, list[Path]]:
        results: dict[str, list[Path]] = {
            "thumbnails": [], "shorts": [], "community": [],
        }
        for _ in range(thumbnails):
            results["thumbnails"].append(self.generate_thumbnail())
        for _ in range(shorts):
            results["shorts"].append(self.generate_short_thumbnail())
        for _ in range(community):
            results["community"].append(self.generate_community_image())
        total = sum(len(v) for v in results.values())
        logger.info("Generated %d total media files", total)
        return results
