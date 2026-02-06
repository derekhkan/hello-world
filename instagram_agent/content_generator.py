"""Content generation — create images, stories, and video reels.

Four modes of operation (tried in order):

1. **Gemini mode** (preferred) — generates photorealistic black-and-white
   gym images via the Nano Banana Pro (Gemini) API, then overlays text.

2. **Brand kit mode** — uses your own downloaded Instagram photos as
   backgrounds with a dark overlay and text on top.

3. **Template mode** (fallback) — renders text on a solid-colour
   background using Pillow.

4. **DALL-E mode** (optional, requires OpenAI key) — generates images
   via DALL-E.

Generated files land in ``media/{posts,stories,reels}/``.
"""

from __future__ import annotations

import logging
import mimetypes
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

# Photorealistic gym scene prompts for Gemini image generation
GYM_SCENE_PROMPTS: list[str] = [
    "Black and white photograph of a power rack with loaded barbell in a garage gym, dramatic side lighting, gritty raw aesthetic, high contrast monochrome",
    "Monochrome close-up of heavy dumbbells on a rack, shallow depth of field, dark moody gym atmosphere, black and white photography",
    "Black and white photograph of a kettlebell on a rubber gym floor with chalk dust, dramatic overhead lighting, raw gritty aesthetic",
    "High contrast black and white photo of weight plates stacked on a barbell, garage gym setting, moody shadows, cinematic composition",
    "Monochrome photograph of a squat rack with iron plates in a home gym, dramatic window light casting shadows, gritty raw style",
    "Black and white close-up of a barbell knurling with chalk, dark gym background, shallow depth of field, high contrast photography",
    "Dramatic monochrome photo of a row of kettlebells on a gym floor, strong directional lighting, raw industrial aesthetic",
    "Black and white photograph of battle ropes coiled on a gym floor, moody low-key lighting, gritty texture, cinematic composition",
    "High contrast monochrome photo of a pull-up bar in a garage gym with concrete walls, dramatic shadows, raw aesthetic",
    "Black and white photograph of a loaded deadlift bar from floor level, chalk dust in the air, dramatic gym lighting",
    "Monochrome close-up of gym chalk on rough hands gripping a barbell, dark background, high contrast black and white",
    "Black and white photo of an empty power cage in a home gym, morning light through garage door, moody atmosphere",
    "Dramatic black and white photo of a medicine ball and jump rope on gym floor, harsh overhead light, raw texture",
    "Monochrome photograph of iron weight plates leaning against a gym wall, dramatic side lighting, gritty industrial feel",
    "Black and white close-up of a adjustable dumbbell set, dark moody background, high contrast photography, shallow focus",
    "High contrast monochrome photo of a bench press station with heavy plates, garage gym, dramatic shadows on concrete floor",
    "Black and white photograph of resistance bands hanging from a pull-up bar, minimalist gym setup, moody lighting",
    "Dramatic monochrome photo of a tire and sledgehammer in a crossfit gym, gritty texture, high contrast black and white",
    "Black and white photograph looking up at a loaded squat bar from below, dramatic perspective, dark gym atmosphere",
    "Monochrome close-up of a gym timer clock on a concrete wall, dark industrial gym setting, high contrast photography",
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
# Gemini (Nano Banana Pro) — photorealistic B&W gym images
# ---------------------------------------------------------------------------

def generate_gemini_background(
    api_key: str,
    size: tuple[int, int] = POST_SIZE,
    scene_prompt: Optional[str] = None,
) -> Optional[Image.Image]:
    """Generate a photorealistic B&W gym image via Gemini Nano Banana Pro.

    Returns ``None`` if generation fails or the package is not installed.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        logger.warning("google-genai not installed — skipping Gemini generation")
        return None

    scene_prompt = scene_prompt or random.choice(GYM_SCENE_PROMPTS)

    # Pick aspect ratio based on target size
    w, h = size
    if abs(w - h) < 100:
        aspect = "1:1"
    elif h > w:
        aspect = "9:16"
    else:
        aspect = "16:9"

    # Try multiple model names — availability depends on API tier
    MODEL_CANDIDATES = [
        "gemini-2.0-flash-exp",
        "gemini-2.0-flash-preview-image-generation",
        "imagen-3.0-generate-002",
    ]

    try:
        client = genai.Client(api_key=api_key)

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=scene_prompt),
                ],
            ),
        ]

        generate_content_config = types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
        )

        for model_name in MODEL_CANDIDATES:
            try:
                logger.info("Trying Gemini model: %s", model_name)
                for chunk in client.models.generate_content_stream(
                    model=model_name,
                    contents=contents,
                    config=generate_content_config,
                ):
                    if chunk.parts is None:
                        continue
                    for part in chunk.parts:
                        if part.inline_data and part.inline_data.data:
                            ext = mimetypes.guess_extension(part.inline_data.mime_type) or ".png"
                            tmp_path = Path(f"/tmp/gemini_{uuid.uuid4().hex[:8]}{ext}")
                            tmp_path.write_bytes(part.inline_data.data)

                            img = Image.open(tmp_path).convert("RGB")
                            tmp_path.unlink(missing_ok=True)

                            img = _center_crop_resize(img, size)
                            logger.info("Gemini generated B&W gym background via %s", model_name)
                            return img
            except Exception as model_err:
                logger.info("Model %s unavailable: %s", model_name, model_err)
                continue

    except Exception as e:
        logger.warning("Gemini image generation failed: %s", e)
        return None

    return None


def generate_gemini_image(
    text: str,
    api_key: str,
    size: tuple[int, int] = POST_SIZE,
    overlay_opacity: float = 0.45,
) -> Optional[Image.Image]:
    """Generate a photorealistic B&W gym photo and overlay text on it."""
    bg = generate_gemini_background(api_key, size)
    if bg is None:
        return None

    # Apply a subtle dark overlay so text is readable
    dark = Image.new("RGB", size, (0, 0, 0))
    img = Image.blend(bg, dark, overlay_opacity)

    # Draw text in white with shadow
    draw = ImageDraw.Draw(img)
    font_size = 64 if size[0] >= 1080 else 44
    _draw_centered_text(draw, text, size, (255, 255, 255), font_size, shadow=True)

    return img


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
# Smart image generator — Gemini → brand kit → template fallback
# ---------------------------------------------------------------------------

# Module-level holder for Gemini API key (set by ContentGenerator)
_gemini_api_key: str = ""


def generate_image(
    text: str,
    size: tuple[int, int] = POST_SIZE,
    palette: Optional[dict] = None,
) -> Image.Image:
    """Generate an image trying these modes in order:
    1. Gemini (photorealistic B&W gym photo) if API key set
    2. Brand kit (your own photos)
    3. Template (solid colour fallback)
    """
    # Try Gemini first
    if _gemini_api_key:
        gemini_img = generate_gemini_image(text, _gemini_api_key, size)
        if gemini_img is not None:
            return gemini_img

    # Try brand kit
    branded = generate_branded_image(text, size)
    if branded is not None:
        return branded

    # Fallback to template
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
        # Set module-level Gemini key so generate_image() can use it
        global _gemini_api_key
        _gemini_api_key = config.gemini_api_key or ""
        if _gemini_api_key:
            logger.info("Gemini (Nano Banana) image generation enabled")

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
