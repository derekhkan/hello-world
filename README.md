# Social Media Automation Agents

A collection of Python agents that automatically generate and publish content across multiple social media platforms on a weekly theme-based schedule, and engage with relevant accounts.

## Platforms

| Platform | Entry Point | Config File | Agent Package |
|---|---|---|---|
| Instagram | `main.py` | `config.yaml` | `instagram_agent/` |
| YouTube | `main_youtube.py` | `youtube_config.yaml` | `youtube_agent/` |
| X (Twitter) | `main_x.py` | `x_config.yaml` | `x_agent/` |
| LinkedIn | `main_linkedin.py` | `linkedin_config.yaml` | `linkedin_agent/` |

Each agent is a **standalone workplace** with its own entry point, configuration, and module package. They share the same architecture and CLI interface.

## Features (All Agents)

- **Weekly theme planner** — describe a theme and the agent generates a full 7-day content calendar
- **Auto-generate media** — creates platform-specific images and graphics using Pillow
- **Optional AI images** — generate images via Gemini or OpenAI DALL-E
- **Auto-publish** — publishes content at scheduled times from the calendar
- **Engagement** — automatically likes and comments on posts from target accounts
- **Content discovery** — finds and engages with relevant content via hashtags/keywords
- **Rate limiting** — configurable random delays between actions
- **Session caching** — reuses login sessions to avoid repeated authentication

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure your platform

```bash
# Pick your platform(s):
cp config.example.yaml config.yaml                    # Instagram
cp youtube_config.example.yaml youtube_config.yaml     # YouTube
cp x_config.example.yaml x_config.yaml                # X (Twitter)
cp linkedin_config.example.yaml linkedin_config.yaml   # LinkedIn
```

Edit the config file with your credentials and preferences. **Never commit config files** — they contain secrets and are already in `.gitignore`.

### 3. Set a weekly theme

```bash
# Instagram
python main.py theme "Staying Disciplined"

# YouTube
python main_youtube.py theme "Staying Disciplined"

# X (Twitter)
python main_x.py theme "Staying Disciplined"

# LinkedIn
python main_linkedin.py theme "Leadership"
```

### 4. Run the agent

```bash
# Daemon mode — publishes on schedule, runs engagement automatically
python main_youtube.py run

# One-shot — runs everything once and exits
python main_x.py run --once
```

### 5. Other commands

```bash
# View current calendar
python main_linkedin.py calendar

# Generate media without posting (preview)
python main_youtube.py generate --thumbnails 3 --shorts 2
python main_x.py generate --tweets 3 --threads 2
python main_linkedin.py generate --posts 3 --carousels 2

# Show/clear flagged accounts
python main_x.py flagged
python main_youtube.py flagged --clear
```

## Platform-Specific Details

### Instagram (`main.py`)
- **Content types**: Posts, Reels, Stories
- **API**: `instagrapi` (unofficial)
- **Auth**: Username/password with challenge & 2FA support
- **Special**: Brand kit downloads, Gemini B&W gym image generation

### YouTube (`main_youtube.py`)
- **Content types**: Videos, Shorts, Community posts
- **API**: YouTube Data API v3 (official)
- **Auth**: OAuth2 via `client_secrets.json` (download from Google Cloud Console)
- **Special**: Custom thumbnail upload, video category/privacy settings

### X / Twitter (`main_x.py`)
- **Content types**: Tweets, Threads, Media posts
- **API**: Twitter API v2 via `tweepy`
- **Auth**: API key + secret + access tokens (from X Developer Portal)
- **Special**: Thread auto-chaining, retweet support, 280-char aware captions

### LinkedIn (`main_linkedin.py`)
- **Content types**: Posts, Articles, Carousels
- **API**: LinkedIn REST API v2 (official)
- **Auth**: OAuth2 access token (3-legged flow, obtained externally)
- **Special**: Image upload via asset registration, professional-tone captions

## Project Structure

```
├── main.py                          # Instagram CLI entry point
├── main_youtube.py                  # YouTube CLI entry point
├── main_x.py                       # X (Twitter) CLI entry point
├── main_linkedin.py                 # LinkedIn CLI entry point
├── config.example.yaml              # Instagram config template
├── youtube_config.example.yaml      # YouTube config template
├── x_config.example.yaml            # X config template
├── linkedin_config.example.yaml     # LinkedIn config template
├── requirements.txt                 # Python dependencies
├── .gitignore
├── fonts/
│   └── LeagueSpartan-Bold.ttf       # Bundled font
├── instagram_agent/
│   ├── __init__.py
│   ├── client.py                    # Auth & session (instagrapi)
│   ├── config.py                    # YAML config loader
│   ├── content_generator.py         # Generate images, stories, reels
│   ├── content_calendar.py          # 7-day theme planner
│   ├── content_manager.py           # Publish to Instagram
│   ├── engagement.py                # Like & comment
│   ├── brand_kit.py                 # Download your own posts
│   └── scheduler.py                 # Job orchestration
├── youtube_agent/
│   ├── __init__.py
│   ├── client.py                    # Auth (OAuth2 / API key)
│   ├── config.py                    # YAML config loader
│   ├── content_generator.py         # Thumbnails, shorts, community
│   ├── content_calendar.py          # 7-day theme planner
│   ├── content_manager.py           # Upload to YouTube
│   ├── engagement.py                # Like & comment on videos
│   └── scheduler.py                 # Job orchestration
├── x_agent/
│   ├── __init__.py
│   ├── client.py                    # Auth (tweepy v2 + v1.1)
│   ├── config.py                    # YAML config loader
│   ├── content_generator.py         # Tweet images, thread visuals
│   ├── content_calendar.py          # 7-day theme planner
│   ├── content_manager.py           # Post tweets, threads
│   ├── engagement.py                # Like, retweet, reply
│   └── scheduler.py                 # Job orchestration
└── linkedin_agent/
    ├── __init__.py
    ├── client.py                    # Auth (OAuth2 bearer token)
    ├── config.py                    # YAML config loader
    ├── content_generator.py         # Post images, article covers
    ├── content_calendar.py          # 7-day theme planner
    ├── content_manager.py           # Publish to LinkedIn
    ├── engagement.py                # Like & comment on posts
    └── scheduler.py                 # Job orchestration
```

## Typical Weekly Workflow

1. **Sunday evening**: Run `theme` for each platform you use
2. **Preview**: Check `media/` folders, swap out any images you don't like
3. **Start agents**: Run each agent in daemon mode (or use a process manager)
4. **Engagement runs automatically**: agents interact with target accounts on schedule
5. **Next Sunday**: Set new themes and repeat

## Important Notes

- Use conservative rate limits to avoid account restrictions on all platforms
- Always test with `--once` before running in daemon mode
- Template-based image generation works offline (no API key needed)
- AI image generation requires a Gemini or OpenAI API key
- Each platform has its own API limitations and terms of service — review them before automating
