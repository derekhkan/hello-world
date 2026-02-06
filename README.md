# Instagram Automation Agent

A Python agent that automatically generates and publishes content (posts, reels, stories) to your Instagram account on a weekly theme-based schedule, and engages with relevant accounts by liking and commenting on their posts.

## Features

- **Weekly theme planner** — describe a theme and the agent generates a full 7-day content calendar
- **Auto-generate media** — creates post images, story graphics, and slideshow reels from text using Pillow
- **Optional AI images** — generate images via OpenAI DALL-E if you provide an API key
- **Auto-publish posts, reels, stories** — publishes content at scheduled times from the calendar
- **Engagement** — automatically likes and comments on posts from target accounts
- **Hashtag discovery** — finds and engages with top posts for relevant hashtags
- **Rate limiting** — configurable random delays between actions to stay within Instagram limits
- **Session caching** — reuses login sessions to avoid repeated authentication

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt

# Optional: for AI image generation
pip install openai

# Optional: for video reel generation
pip install moviepy numpy
```

### 2. Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your Instagram credentials, posting schedule, target accounts, and engagement preferences. **Never commit `config.yaml`** — it contains your password and is already in `.gitignore`.

### 3. Set a weekly theme and generate content

This is the main workflow. Describe the theme you want to hit this week:

```bash
python main.py theme "Minimalist productivity"
```

This will:
1. Create a 7-day content calendar (14 items: mix of posts, reels, stories)
2. Generate all the media (images + video) up front
3. Save the calendar to `calendar.json`
4. Print a summary like:

```
Content Calendar — "Minimalist productivity"
Starts: 2025-06-15
Total items: 14

  2025-06-15
    09:00  [post ] Week kick-off: Minimalist productivity — let's go!  (pending)
    12:00  [story] Behind the scenes: getting ready for a week of ...  (pending)
  2025-06-16
    09:00  [post ] Day 2 of Minimalist productivity: diving deeper.    (pending)
    18:00  [story] Quick tip about Minimalist productivity.            (pending)
  ...
```

### 4. Run the agent

**Daemon mode** — publishes calendar items at their scheduled times and runs engagement:

```bash
python main.py run
```

**One-shot mode** — publishes everything due right now and exits:

```bash
python main.py run --once
```

### 5. Other commands

```bash
# View the current calendar
python main.py calendar

# Generate media files without posting (for preview)
python main.py generate --posts 3 --stories 2 --reels 1
```

## Typical Weekly Workflow

1. **Sunday evening**: Run `python main.py theme "This week's theme"` — generates all content
2. **Preview**: Check the `media/` folder, swap out any images you don't like
3. **Start the agent**: `python main.py run` — it publishes on schedule all week
4. **Engagement runs automatically**: likes and comments on target accounts every few hours
5. **Next Sunday**: Set a new theme and repeat

## Project Structure

```
├── main.py                              # CLI entry point
├── config.example.yaml                  # Example configuration
├── requirements.txt                     # Python dependencies
├── .gitignore
└── instagram_agent/
    ├── __init__.py
    ├── client.py                        # Auth & session management
    ├── config.py                        # YAML config loader
    ├── content_generator.py             # Generate images, stories, reels
    ├── content_calendar.py              # 7-day theme planner + calendar
    ├── content_manager.py               # Publish content to Instagram
    ├── engagement.py                    # Like & comment on target accounts
    └── scheduler.py                     # Time-based job orchestration
```

## Configuration Reference

See `config.example.yaml` for all available options. Key sections:

| Section | Purpose |
|---|---|
| `account` | Instagram username and password |
| `content.schedule` | Per-type posting times (posts, reels, stories) |
| `content.defaults` | Default hashtags and location |
| `generation` | Content generation settings (quotes, AI, palettes) |
| `generation.ai` | DALL-E settings (optional, requires OpenAI key) |
| `engagement.target_accounts` | Accounts whose posts you want to like/comment |
| `engagement.discovery_hashtags` | Hashtags to explore for new content |
| `engagement.delay` | Min/max seconds between API calls |

## Important Notes

- This agent uses the unofficial `instagrapi` library. Instagram may change its private API at any time.
- Aggressive automation can lead to temporary or permanent account restrictions. Use conservative rate limits.
- Always test with `python main.py run --once` before running in daemon mode.
- Template-based image generation works offline with just Pillow (no API key needed).
- AI image generation requires an OpenAI API key and `pip install openai`.
- Video reel generation requires `pip install moviepy numpy`.
