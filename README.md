# Instagram Automation Agent

A Python agent that automatically publishes content (posts, reels, stories) to your Instagram account and engages with relevant accounts by liking and commenting on their posts.

## Features

- **Auto-publish posts** — schedule photo and video posts at specific times
- **Auto-publish reels** — schedule `.mp4` clips as Instagram Reels
- **Auto-publish stories** — schedule photo/video stories
- **Engagement** — automatically like and comment on posts from target accounts
- **Hashtag discovery** — find and engage with top posts for relevant hashtags
- **Rate limiting** — configurable random delays between actions to stay within Instagram limits
- **Session caching** — reuses login sessions to avoid repeated authentication

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your Instagram credentials, posting schedule, target accounts, and engagement preferences. **Never commit `config.yaml`** — it contains your password and is already in `.gitignore`.

### 3. Add media

Create the media directory structure:

```
media/
├── posts/       # .jpg, .png, or .mp4 files
├── reels/       # .mp4 files
└── stories/     # .jpg, .png, or .mp4 files
```

For captions, place a `.txt` file with the same name as the media file (e.g., `sunset.jpg` + `sunset.txt`), or add a `caption.txt` in the directory to use as a default.

### 4. Run

**Daemon mode** (runs on schedule continuously):

```bash
python main.py --config config.yaml
```

**One-shot mode** (runs all jobs once, then exits):

```bash
python main.py --config config.yaml --once
```

## Project Structure

```
├── main.py                          # CLI entry point
├── config.example.yaml              # Example configuration
├── requirements.txt                 # Python dependencies
├── .gitignore
└── instagram_agent/
    ├── __init__.py
    ├── client.py                    # Auth & session management
    ├── config.py                    # YAML config loader
    ├── content_manager.py           # Publish posts, reels, stories
    ├── engagement.py                # Like & comment on target accounts
    └── scheduler.py                 # Time-based job orchestration
```

## Configuration Reference

See `config.example.yaml` for all available options. Key sections:

| Section | Purpose |
|---|---|
| `account` | Instagram username and password |
| `content.schedule` | Per-type posting times (posts, reels, stories) |
| `content.defaults` | Default hashtags and location |
| `engagement.target_accounts` | Accounts whose posts you want to like/comment |
| `engagement.discovery_hashtags` | Hashtags to explore for new content |
| `engagement.delay` | Min/max seconds between API calls |

## Important Notes

- This agent uses the unofficial `instagrapi` library. Instagram may change its private API at any time.
- Aggressive automation can lead to temporary or permanent account restrictions. Use conservative rate limits.
- Always test with `--once` before running in daemon mode.
