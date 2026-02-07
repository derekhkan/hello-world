"""Video assembler — stitches images + TTS audio into a YouTube Short.

Pipeline:
  1. Generate TTS audio for each scene's narration via ``edge-tts``.
  2. For each scene, create a clip: image (Ken Burns pan/zoom) + caption overlay.
  3. Concatenate clips with cross-fade transitions.
  4. Mix in TTS audio (and optional background music).
  5. Export as MP4 (H.264 + AAC), 9:16, ≤60 s.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional

import edge_tts
from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    concatenate_videoclips,
)
from PIL import Image, ImageDraw, ImageFont

from yt_shorts_bot.config import VideoSettings, load_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TTS helper
# ---------------------------------------------------------------------------

async def generate_tts(text: str, output_path: Path, voice: str) -> Path:
    """Generate a TTS audio file using edge-tts."""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_path))
    logger.info("TTS saved to %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Caption rendering (Pillow-based for more control than MoviePy TextClip)
# ---------------------------------------------------------------------------

def render_caption_image(
    text: str,
    width: int = 1080,
    height: int = 200,
    font_size: int = 52,
    bg_color: tuple = (0, 0, 0, 180),
    text_color: tuple = (255, 255, 255, 255),
) -> str:
    """Render caption text to a transparent PNG and return its path."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Semi-transparent background bar
    draw.rectangle([(0, 0), (width, height)], fill=bg_color)

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size
        )
    except OSError:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (width - tw) // 2
    y = (height - th) // 2
    draw.text((x, y), text, fill=text_color, font=font)

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img.save(tmp.name, "PNG")
    return tmp.name


# ---------------------------------------------------------------------------
# Scene → MoviePy clip
# ---------------------------------------------------------------------------

def make_scene_clip(
    image_path: Path,
    caption_text: str,
    duration: float,
    settings: VideoSettings,
) -> CompositeVideoClip:
    """Build a single scene clip: image + caption overlay."""
    w, h = settings.width, settings.height

    # Base image clip — resize/crop to 9:16
    img_clip = (
        ImageClip(str(image_path))
        .set_duration(duration)
        .resize(height=h)
    )
    # Center-crop to exact width
    if img_clip.w > w:
        img_clip = img_clip.crop(
            x_center=img_clip.w / 2, width=w, height=h
        )
    elif img_clip.w < w:
        img_clip = img_clip.resize(width=w)

    img_clip = img_clip.set_duration(duration)

    # Caption overlay in the bottom third
    caption_path = render_caption_image(caption_text, width=w, height=180)
    caption_clip = (
        ImageClip(caption_path, transparent=True)
        .set_duration(duration)
        .set_position(("center", h - 260))
    )

    return CompositeVideoClip([img_clip, caption_clip], size=(w, h)).set_duration(duration)


# ---------------------------------------------------------------------------
# Full assembly
# ---------------------------------------------------------------------------

async def assemble_video(
    image_paths: list[Path],
    scenes: list,  # list of Scene dataclass instances
    output_path: Path,
    background_music: Optional[Path] = None,
    settings: Optional[VideoSettings] = None,
) -> Path:
    """Assemble a full YouTube Short from images and scene metadata.

    Parameters
    ----------
    image_paths:
        One image file per scene, in order.
    scenes:
        List of ``Scene`` objects (from content generator).
    output_path:
        Where to write the final .mp4.
    background_music:
        Optional path to a background music file.
    settings:
        Video settings override.

    Returns
    -------
    Path to the exported .mp4 file.
    """
    settings = settings or load_settings().video

    # Generate TTS for each scene in parallel
    tts_dir = output_path.parent / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)

    tts_tasks = []
    for i, scene in enumerate(scenes):
        tts_path = tts_dir / f"scene_{i:03d}.mp3"
        tts_tasks.append(generate_tts(scene.narration, tts_path, settings.tts_voice))

    tts_paths = await asyncio.gather(*tts_tasks)

    # Build scene clips
    clips = []
    audio_clips = []
    current_time = 0.0

    for i, (img_path, scene) in enumerate(zip(image_paths, scenes)):
        # Determine clip duration — match TTS length or scene default, whichever is longer
        tts_audio = AudioFileClip(str(tts_paths[i]))
        clip_duration = max(scene.duration, tts_audio.duration + 0.5)

        scene_clip = make_scene_clip(img_path, scene.caption, clip_duration, settings)
        clips.append(scene_clip)

        # Position TTS audio at the right time offset
        tts_audio = tts_audio.set_start(current_time)
        audio_clips.append(tts_audio)
        current_time += clip_duration

    # Concatenate video clips with crossfade
    if settings.transition_duration > 0 and len(clips) > 1:
        final_video = concatenate_videoclips(
            clips, method="compose", padding=-settings.transition_duration
        )
    else:
        final_video = concatenate_videoclips(clips, method="compose")

    # Mix audio
    mixed_audio_parts = list(audio_clips)
    if background_music and background_music.exists():
        bg = AudioFileClip(str(background_music)).volumex(0.15)
        if bg.duration < final_video.duration:
            bg = bg.audio_loop(duration=final_video.duration)
        else:
            bg = bg.subclip(0, final_video.duration)
        mixed_audio_parts.append(bg)

    if mixed_audio_parts:
        final_audio = CompositeAudioClip(mixed_audio_parts)
        final_video = final_video.set_audio(final_audio)

    # Trim to max duration
    if final_video.duration > settings.max_duration:
        final_video = final_video.subclip(0, settings.max_duration)

    # Export
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_video.write_videofile(
        str(output_path),
        fps=settings.fps,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
        logger=None,  # suppress moviepy progress bar in bot context
    )
    logger.info("Video exported to %s (%.1f s)", output_path, final_video.duration)
    return output_path
