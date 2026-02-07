# YouTube Shorts Bot

Automated YouTube Shorts creation and publishing bot. Generates AI-powered short-form vertical videos using Midjourney for images, edge-tts for narration, and MoviePy for video assembly, then uploads directly to YouTube.

## Features

- **Content generation** with built-in themes ("Nano Banana", "Cosmic Fruit") and custom YAML themes
- **AI image generation** via Midjourney API (with local placeholder fallback for testing)
- **Video assembly** — stitches images into 9:16 vertical video with captions, TTS narration, transitions, and optional background music
- **YouTube upload** via the YouTube Data API v3 with OAuth2 authentication
- **CLI interface** for one-command generation and publishing

## Quick Start

### 1. Install

```bash
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your API keys
```

**Required credentials:**

| Credential | How to get it |
|---|---|
| `MIDJOURNEY_API_KEY` | Sign up for a Midjourney proxy API (GoAPI, ImagineAPI, etc.) |
| `client_secrets.json` | Create an OAuth2 app in [Google Cloud Console](https://console.cloud.google.com/) with YouTube Data API v3 enabled, download the client secrets JSON |

### 3. Run

```bash
# Generate a video locally (no upload)
yt-shorts-bot generate

# Generate with a specific theme
yt-shorts-bot generate --theme nano_banana --scenes 5

# Generate AND upload to YouTube
yt-shorts-bot generate --upload

# Upload an existing video
yt-shorts-bot upload video.mp4 --title "My Short" --description "Cool video"

# List available themes
yt-shorts-bot themes

# Preview a script (no images or video)
yt-shorts-bot script-only
```

### Custom Variables

```bash
yt-shorts-bot generate --theme nano_banana --var size=42
yt-shorts-bot generate --theme cosmic_fruit --var fruit=pineapple
```

## Project Structure

```
yt_shorts_bot/
  __init__.py          # Package init
  config.py            # Settings (env vars, .env, defaults)
  cli.py               # Click CLI entry point
  bot.py               # Pipeline orchestrator
  content/
    generator.py       # Script/content generation with themes
    themes/            # Custom theme YAML files
  images/
    midjourney.py      # Midjourney API client + placeholder fallback
  video/
    assembler.py       # MoviePy video assembly + edge-tts
  youtube/
    uploader.py        # YouTube Data API v3 OAuth2 upload
  assets/              # Static assets (fonts, music, etc.)
```

## Custom Themes

Create a YAML file (see `yt_shorts_bot/content/themes/example_custom.yaml`):

```yaml
name: my_theme
hook_templates:
  - "This will blow your mind."
scene_templates:
  - image_prompt: "a surreal scene, cinematic, 8k"
    narration: "Something incredible happened."
    caption: "wow"
outro_templates:
  - "Follow for more."
tag_pool: [shorts, viral, ai]
```

Then run:

```bash
yt-shorts-bot generate --custom-theme my_theme.yaml
```

## How It Works

1. **Script generation** — picks a theme, randomizes scenes, creates Midjourney prompts + narration text + captions
2. **Image generation** — sends each prompt to Midjourney API, downloads resulting images (or generates placeholders if no API key)
3. **Video assembly** — generates TTS audio via edge-tts, composites images with caption overlays, concatenates with crossfade transitions, mixes audio
4. **YouTube upload** — authenticates via OAuth2, uploads as a resumable media upload with #Shorts metadata

## Requirements

- Python 3.10+
- FFmpeg (required by MoviePy for video encoding)
- A Midjourney proxy API key (optional — placeholders work for testing)
- Google Cloud OAuth2 credentials with YouTube Data API v3 (required for upload)
