"""Content generation — create images, stories, and video reels.

Three modes of operation:

1. **Brand kit mode** (preferred) — uses your own downloaded Instagram
   photos as backgrounds with a dark overlay and text on top.

2. **Template mode** (fallback) — renders text on a solid-colour
   background using Pillow.

3. **AI mode** (optional, requires OpenAI key) — generates images via
   DALL-E.

Generated files land in ``media/{posts,stories,reels}/``.
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

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

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
    ai_prompts: List[str] = field(default_factory=list)
    media_dir: str = "./media"


# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
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
    """Word-wrap *text* and draw it centered on the canvas."""
    font = _load_font(font_size)
    wrapped = textwrap.fill(text, width=22)
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
# Brand kit image (photo background + dark overlay + white text)
# ---------------------------------------------------------------------------

def _get_brand_kit_photos() -> list[Path]:
    """Return all photos in the brand kit directory."""
    if not BRAND_KIT_DIR.exists():
        return []
    return sorted(
        p for p in BRAND_KIT_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}
    )


def generate_branded_image(
    text: str,
    size: tuple[int, int] = POST_SIZE,
    overlay_opacity: float = 0.55,
) -> Optional[Image.Image]:
    """Create an image using a random brand kit photo as the background.

    Returns ``None`` if no brand kit photos are available.
    """
    photos = _get_brand_kit_photos()
    if not photos:
        return None

    bg_path = random.choice(photos)
    bg = Image.open(bg_path).convert("RGB")

    # Crop/resize to target size (center crop)
    bg = _center_crop_resize(bg, size)

    # Darken the photo so white text is readable
    dark_overlay = Image.new("RGB", size, (0, 0, 0))
    bg = Image.blend(bg, dark_overlay, overlay_opacity)

    # Slight blur to push background further back
    bg = bg.filter(ImageFilter.GaussianBlur(radius=2))

    # Draw text in white with shadow
    draw = ImageDraw.Draw(bg)
    font_size = 60 if size[0] >= 1080 else 40
    _draw_centered_text(draw, text, size, (255, 255, 255), font_size, shadow=True)

    return bg


def _center_crop_resize(img: Image.Image, target: tuple[int, int]) -> Image.Image:
    """Resize and center-crop *img* to exactly *target* dimensions."""
    tw, th = target
    iw, ih = img.size

    # Scale so the smaller dimension matches the target
    scale = max(tw / iw, th / ih)
    new_w = int(iw * scale)
    new_h = int(ih * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # Center crop
    left = (new_w - tw) // 2
    top = (new_h - th) // 2
    return img.crop((left, top, left + tw, top + th))


# ---------------------------------------------------------------------------
# Template-based (solid colour background)
# ---------------------------------------------------------------------------

def generate_template_image(
    text: str,
    size: tuple[int, int] = POST_SIZE,
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


# ---------------------------------------------------------------------------
# Smart image generator — brand kit first, template fallback
# ---------------------------------------------------------------------------

def generate_image(
    text: str,
    size: tuple[int, int] = POST_SIZE,
    palette: Optional[dict] = None,
) -> Image.Image:
    """Generate an image using the brand kit if available, otherwise fall
    back to template mode."""
    branded = generate_branded_image(text, size)
    if branded is not None:
        return branded
    return generate_template_image(text, size, palette)


# ---------------------------------------------------------------------------
# AI image generator (DALL-E)
# ---------------------------------------------------------------------------

def generate_ai_image(
    prompt: str,
    api_key: str,
    size: str = "1024x1024",
    output_path: Optional[Path] = None,
) -> Path:
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

    import urllib.request
    if output_path is None:
        output_path = Path(f"/tmp/dalle_{uuid.uuid4().hex[:8]}.png")

    urllib.request.urlretrieve(image_url, str(output_path))
    logger.info("AI image saved to %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Video reel generator
# ---------------------------------------------------------------------------

def generate_slideshow_reel(
    texts: List[str],
    output_path: Path,
    duration_per_slide: float = 3.0,
    fps: int = 24,
    size: tuple[int, int] = REEL_SIZE,
    palettes: Optional[list[dict]] = None,
) -> Path:
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
        img = generate_image(text, size=size, palette=palettes[i % len(palettes)])
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
# High-level generator
# ---------------------------------------------------------------------------

class ContentGenerator:
    """Generate media files and drop them into ``media/`` for publishing."""

    def __init__(self, config: GenerationConfig) -> None:
        self._cfg = config
        self._media_dir = Path(config.media_dir)

    def _ensure_dirs(self) -> None:
        for sub in ("posts", "reels", "stories"):
            (self._media_dir / sub).mkdir(parents=True, exist_ok=True)

    def generate_post(self, text: Optional[str] = None) -> Path:
        self._ensure_dirs()
        text = text or random.choice(self._cfg.quotes)
        img = generate_image(text, POST_SIZE)
        fname = f"post_{uuid.uuid4().hex[:8]}.png"
        path = self._media_dir / "posts" / fname
        img.save(str(path))

        caption_path = path.with_suffix(".txt")
        caption_path.write_text(text)

        logger.info("Generated post: %s", path)
        return path

    def generate_ai_post(self, prompt: Optional[str] = None) -> Path:
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

    def generate_story(self, text: Optional[str] = None) -> Path:
        self._ensure_dirs()
        text = text or random.choice(self._cfg.quotes)
        img = generate_image(text, STORY_SIZE)
        fname = f"story_{uuid.uuid4().hex[:8]}.png"
        path = self._media_dir / "stories" / fname
        img.save(str(path))
        logger.info("Generated story: %s", path)
        return path

    def generate_reel(
        self,
        texts: Optional[List[str]] = None,
        slides: int = 4,
    ) -> Path:
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

    def generate_batch(
        self,
        posts: int = 1,
        stories: int = 1,
        reels: int = 0,
    ) -> dict[str, list[Path]]:
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
